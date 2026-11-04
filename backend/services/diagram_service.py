"""
Diagram orchestration service.

Ties together all agents and modules to process a diagram request end-to-end.
This is the single integration point called by the FastAPI route handlers.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Optional

from backend.agents.granite_client import GraniteClient
from backend.agents.intent_agent import IntentAgent
from backend.agents.technical_reasoning_agent import TechnicalReasoningAgent
from backend.ir.schema import DiagramIR
from backend.layout.engine import run_layout
from backend.tikz.generator import TikZGenerator
from backend.compiler.latex_compiler import LatexCompiler, CompilationResult
from backend.validation.pipeline import ValidationPipeline, ValidationReport
from backend.research.research_manager import ResearchAgent, ResearchContext
from backend.sketch.image_parser import SketchInterpreter
from backend.config import get_settings

logger = logging.getLogger(__name__)


class DiagramResult:
    __slots__ = (
        "diagram_id", "ir", "tikz_code",
        "pdf_b64", "png_b64",
        "status", "compilation_success", "compilation_log",
        "agent_summary",
        "validation_report", "research_context",
    )

    def __init__(
        self,
        diagram_id: str,
        ir: DiagramIR,
        tikz_code: str,
        pdf_b64: Optional[str],
        png_b64: Optional[str],
        status: str,
        agent_summary: str,
        validation_report: Optional[ValidationReport],
        research_context: Optional[ResearchContext],
        compilation_success: bool = True,
        compilation_log: str = "",
    ) -> None:
        self.diagram_id = diagram_id
        self.ir = ir
        self.tikz_code = tikz_code
        self.pdf_b64 = pdf_b64
        self.png_b64 = png_b64
        self.status = status
        self.compilation_success = compilation_success
        self.compilation_log = compilation_log
        self.agent_summary = agent_summary
        self.validation_report = validation_report
        self.research_context = research_context

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "diagram_id": self.diagram_id,
            "status": self.status,
            "compilation_success": self.compilation_success,
            "agent_summary": self.agent_summary,
            "ir": self.ir.to_dict(),
            "tikz_code": self.tikz_code,
        }
        if self.pdf_b64:
            result["pdf_base64"] = self.pdf_b64
        if self.png_b64:
            result["png_base64"] = self.png_b64
        if not self.compilation_success and self.compilation_log:
            result["compilation_log"] = self.compilation_log
        if self.validation_report:
            result["validation"] = {
                "passed": self.validation_report.passed,
                "errors": self.validation_report.all_errors,
                "warnings": self.validation_report.all_warnings,
            }
        if self.research_context and self.research_context.technical_summary:
            result["research"] = {
                "summary": self.research_context.technical_summary,
                "components": self.research_context.component_list,
                "sources": [
                    {"url": s.url, "title": s.title}
                    for s in self.research_context.results
                ],
            }
        return result


class DiagramService:
    """
    End-to-end diagram generation and refinement service.
    Instantiate once at application start and reuse.
    """

    def __init__(self) -> None:
        self._client = GraniteClient()
        self._intent = IntentAgent(self._client)
        self._reasoner = TechnicalReasoningAgent(self._client)
        self._research = ResearchAgent(self._client)
        self._sketch = SketchInterpreter(self._client)
        self._tikz_gen = TikZGenerator()
        self._compiler = LatexCompiler()
        self._validator = ValidationPipeline()

    # ── Generate ──────────────────────────────────────────────────────────────

    def generate(
        self,
        prompt: str,
        sketch_b64: Optional[str] = None,
        enable_research: bool = False,
    ) -> DiagramResult:
        diagram_id = uuid.uuid4().hex
        research_ctx: Optional[ResearchContext] = None

        # 1. Optionally research the topic
        if enable_research and prompt.strip():
            try:
                research_ctx = self._research.research(prompt)
                prompt = self._research.enhance_prompt(prompt, research_ctx)
                logger.info("Research complete for: %s", prompt[:60])
            except Exception as exc:
                logger.warning("Research failed (non-fatal): %s", exc)

        # 2. Build IR from sketch or text
        if sketch_b64:
            ir = self._sketch.interpret(sketch_b64, additional_notes=prompt)
        else:
            ir = self._intent.generate_ir(prompt)

        ir.id = diagram_id

        # 3. Technical review (non-blocking)
        try:
            review = self._reasoner.review(ir)
            if review.issues:
                ir.validation.warnings.extend(review.issues)
        except Exception as exc:
            logger.warning("Technical reasoning failed (non-fatal): %s", exc)

        # 4. Layout
        ir = run_layout(ir)

        # 5. Generate TikZ
        tikz_code = self._tikz_gen.generate(ir)

        # 6. Validate and repair
        report, tikz_code = self._validator.run_full(
            ir, tikz_code, granite_client=self._client
        )

        # 7. Compile
        compiled = self._compiler.compile(tikz_code)

        return DiagramResult(
            diagram_id=diagram_id,
            ir=ir,
            tikz_code=tikz_code,
            pdf_b64=compiled.pdf_b64,
            png_b64=compiled.png_b64,
            status=compiled.status,
            agent_summary=ir.agent_summary or "Diagram generated.",
            validation_report=report,
            research_context=research_ctx,
            compilation_success=compiled.success,
            compilation_log=compiled.log,
        )

    # ── Refine ────────────────────────────────────────────────────────────────

    def refine(
        self,
        current_ir_dict: dict[str, Any],
        instruction: str,
        current_tikz: str = "",
    ) -> DiagramResult:
        # Restore the IR object
        current_ir = DiagramIR.from_dict(current_ir_dict)

        # Determine routing
        route = self._intent.route_command(instruction)

        if route == "NEW_DIAGRAM":
            return self.generate(instruction)

        if route != "STYLE_TIKZ":
            # Structural update through IR
            try:
                updated_ir = self._intent.refine_ir(current_ir, instruction)
                updated_ir = run_layout(updated_ir)
                tikz_code = self._tikz_gen.generate(updated_ir)
                report, tikz_code = self._validator.run_full(
                    updated_ir, tikz_code, granite_client=self._client
                )
                compiled = self._compiler.compile(tikz_code)
                if compiled.success:
                    return DiagramResult(
                        diagram_id=updated_ir.id,
                        ir=updated_ir,
                        tikz_code=tikz_code,
                        pdf_b64=compiled.pdf_b64,
                        png_b64=compiled.png_b64,
                        status=compiled.status,
                        agent_summary=updated_ir.agent_summary or "Diagram refined.",
                        validation_report=report,
                        research_context=None,
                        compilation_success=True,
                        compilation_log=compiled.log,
                    )
            except Exception as exc:
                logger.warning("IR refinement failed, falling back to TikZ edit: %s", exc)

        # Direct TikZ style edit
        if not current_tikz:
            current_tikz = self._tikz_gen.generate(current_ir)

        from backend.tikz.repair_prompts import TIKZ_REPAIR_SYSTEM_PROMPT
        user_msg = (
            f"Current TikZ code:\n```latex\n{current_tikz}\n```\n\n"
            f"Refinement request: {instruction}\n\n"
            "Provide the complete updated standalone LaTeX code inside ```latex ... ``` blocks:"
        )
        import re
        raw = self._client.chat(TIKZ_REPAIR_SYSTEM_PROMPT, user_msg)
        match = re.search(r"```(?:latex|tex)?\s*(.*?)```", raw, re.DOTALL)
        candidate = match.group(1).strip() if match else raw.strip()

        compiled = self._compiler.compile(candidate)
        if compiled.success:
            current_ir.agent_summary = f"TikZ style edit: {instruction[:50]}"
            return DiagramResult(
                diagram_id=current_ir.id,
                ir=current_ir,
                tikz_code=candidate,
                pdf_b64=compiled.pdf_b64,
                png_b64=compiled.png_b64,
                status=compiled.status,
                agent_summary=current_ir.agent_summary,
                validation_report=None,
                research_context=None,
                compilation_success=True,
                compilation_log=compiled.log,
            )

        # Final fallback – return current unchanged with error status
        return DiagramResult(
            diagram_id=current_ir.id,
            ir=current_ir,
            tikz_code=current_tikz,
            pdf_b64=None,
            png_b64=None,
            status=f"Refinement compilation failed: {compiled.status}",
            agent_summary="Refinement failed – returning previous state.",
            validation_report=None,
            research_context=None,
            compilation_success=False,
            compilation_log=compiled.log,
        )

    # ── Research ──────────────────────────────────────────────────────────────

    def research_topic(self, topic: str) -> ResearchContext:
        return self._research.research(topic)
