"""
Validation and Automatic Repair Pipeline.

Stages:
  1. Semantic validation
  2. Graph validation
  3. Geometric validation
  4. Typography validation
  5. Compilation validation
  6. Automatic repair (Granite-assisted)
"""
from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass, field
from typing import Optional

from backend.ir.schema import DiagramIR, ValidationResult, DiagramCategory
from backend.config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class ValidationReport:
    passed: bool = True
    stage_results: dict[str, ValidationResult] = field(default_factory=dict)

    @property
    def all_errors(self) -> list[str]:
        errors = []
        for vr in self.stage_results.values():
            errors.extend(vr.errors)
        return errors

    @property
    def all_warnings(self) -> list[str]:
        warnings = []
        for vr in self.stage_results.values():
            warnings.extend(vr.warnings)
        return warnings


class ValidationPipeline:
    """Runs all validation stages against an IR and its compiled output."""

    def __init__(self) -> None:
        self.cfg = get_settings()

    # ── Stage 1: Semantic ─────────────────────────────────────────────────────

    def validate_semantic(self, ir: DiagramIR) -> ValidationResult:
        errors: list[str] = []
        warnings: list[str] = []

        if not ir.nodes:
            errors.append("IR contains no nodes.")

        node_ids = {n.id for n in ir.nodes}
        group_ids = {g.id for g in ir.groups}

        for edge in ir.edges:
            if edge.from_node not in node_ids:
                errors.append(f"Edge '{edge.id}': from_node '{edge.from_node}' not in nodes.")
            if edge.to_node not in node_ids:
                errors.append(f"Edge '{edge.id}': to_node '{edge.to_node}' not in nodes.")

        for node in ir.nodes:
            if node.group and node.group not in group_ids:
                warnings.append(
                    f"Node '{node.id}' references group '{node.group}' which is not defined."
                )

        # Category-specific semantic checks
        if ir.category == DiagramCategory.UML_SEQUENCE:
            if not any(e.label for e in ir.edges):
                warnings.append(
                    "UML Sequence diagram has no labeled messages. "
                    "Message labels are required for sequence diagrams."
                )

        if ir.category == DiagramCategory.QUANTUM_CIRCUIT:
            qubit_nodes = [n for n in ir.nodes if n.qubit_index is not None]
            if not qubit_nodes:
                warnings.append(
                    "Quantum circuit has no nodes with qubit_index set. "
                    "Set qubit_index on each gate node."
                )

        return ValidationResult(
            passed=len(errors) == 0,
            stage="semantic",
            errors=errors,
            warnings=warnings,
        )

    # ── Stage 2: Graph ────────────────────────────────────────────────────────

    def validate_graph(self, ir: DiagramIR) -> ValidationResult:
        errors: list[str] = []
        warnings: list[str] = []
        node_ids = {n.id for n in ir.nodes}

        # Check connectivity – warn if any node has no edges
        connected = set()
        for e in ir.edges:
            connected.add(e.from_node)
            connected.add(e.to_node)
        isolated = node_ids - connected
        if isolated and len(ir.nodes) > 1:
            warnings.append(
                f"Isolated nodes (no connections): {', '.join(sorted(isolated))}"
            )

        # Detect self-loop edges that might be intentional
        for e in ir.edges:
            if e.from_node == e.to_node:
                warnings.append(
                    f"Self-loop edge '{e.id}' on node '{e.from_node}'. "
                    "If intentional, use routing='self_loop'."
                )

        return ValidationResult(
            passed=len(errors) == 0,
            stage="graph",
            errors=errors,
            warnings=warnings,
        )

    # ── Stage 3: Geometric ────────────────────────────────────────────────────

    def validate_geometry(self, ir: DiagramIR) -> ValidationResult:
        errors: list[str] = []
        warnings: list[str] = []

        # 1. Check for overlapping node bounding boxes (exact center-based coords)
        for i, na in enumerate(ir.nodes):
            for nb in ir.nodes[i + 1:]:
                ax1 = na.geometry.x - na.geometry.width / 2.0
                ax2 = na.geometry.x + na.geometry.width / 2.0
                ay1 = na.geometry.y - na.geometry.height / 2.0
                ay2 = na.geometry.y + na.geometry.height / 2.0

                bx1 = nb.geometry.x - nb.geometry.width / 2.0
                bx2 = nb.geometry.x + nb.geometry.width / 2.0
                by1 = nb.geometry.y - nb.geometry.height / 2.0
                by2 = nb.geometry.y + nb.geometry.height / 2.0

                x_overlap = ax1 < bx2 and ax2 > bx1
                y_overlap = ay1 < by2 and ay2 > by1
                if x_overlap and y_overlap:
                    warnings.append(
                        f"Nodes '{na.id}' and '{nb.id}' bounding boxes overlap."
                    )

        # 2. Check for overlapping group containers
        for i, ga in enumerate(ir.groups):
            for gb in ir.groups[i + 1:]:
                gax1 = ga.geometry.x
                gax2 = ga.geometry.x + ga.geometry.width
                gay1 = ga.geometry.y
                gay2 = ga.geometry.y + ga.geometry.height

                gbx1 = gb.geometry.x
                gbx2 = gb.geometry.x + gb.geometry.width
                gby1 = gb.geometry.y
                gby2 = gb.geometry.y + gb.geometry.height

                if gax1 < gbx2 and gax2 > gbx1 and gay1 < gby2 and gay2 > gby1:
                    warnings.append(
                        f"Groups '{ga.id}' and '{gb.id}' bounding boxes overlap."
                    )

        # 3. Check for foreign nodes inside group containers
        for g in ir.groups:
            gx1 = g.geometry.x
            gx2 = g.geometry.x + g.geometry.width
            gy1 = g.geometry.y
            gy2 = g.geometry.y + g.geometry.height
            for n in ir.nodes:
                if n.group != g.id:
                    nx1 = n.geometry.x - n.geometry.width / 2.0
                    nx2 = n.geometry.x + n.geometry.width / 2.0
                    ny1 = n.geometry.y - n.geometry.height / 2.0
                    ny2 = n.geometry.y + n.geometry.height / 2.0
                    if gx1 < nx2 and gx2 > nx1 and gy1 < ny2 and gy2 > ny1:
                        warnings.append(
                            f"Foreign node '{n.id}' overlaps group container '{g.id}'."
                        )

        return ValidationResult(
            passed=len(errors) == 0,
            stage="geometry",
            errors=errors,
            warnings=warnings,
        )

    # ── Stage 4: Typography ───────────────────────────────────────────────────

    def validate_typography(self) -> ValidationResult:
        errors: list[str] = []
        warnings: list[str] = []
        cfg = get_settings()

        if cfg.use_fontspec:
            # Check if the preferred font is available (font file on PATH)
            import subprocess
            try:
                result = subprocess.run(
                    ["fc-list", ":family=Times New Roman"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if not result.stdout.strip():
                    warnings.append(
                        f"Font '{cfg.preferred_font}' not found via fc-list. "
                        f"Consider setting USE_FONTSPEC=false to use mathptmx fallback."
                    )
            except Exception:
                # fc-list not available — skip check
                pass
        else:
            # pdflatex path: mathptmx approximates Times New Roman
            if not shutil.which("pdflatex"):
                warnings.append(
                    "pdflatex not found locally. Remote compiler fallback (texlive.net) will be used."
                )

        return ValidationResult(
            passed=len(errors) == 0,
            stage="typography",
            errors=errors,
            warnings=warnings,
        )

    # ── Stage 5: Compilation ──────────────────────────────────────────────────

    def validate_compilation(self, tikz_code: str) -> ValidationResult:
        """Attempt to compile the tikz_code and report results."""
        from backend.compiler.latex_compiler import LatexCompiler

        compiler = LatexCompiler()
        result = compiler.compile(tikz_code)
        errors = [] if result.success else [
            f"Compilation failed: {result.status}\n{result.log[-2000:] if result.log else ''}"
        ]
        return ValidationResult(
            passed=result.success,
            stage="compilation",
            errors=errors,
            warnings=[],
        )

    # ── Stage 6: Repair ───────────────────────────────────────────────────────

    def repair_tikz(
        self,
        tikz_code: str,
        error_log: str,
        granite_client=None,
    ) -> Optional[str]:
        """
        Use Granite to repair broken TikZ code.
        Returns the repaired code or None if no client is available.
        """
        if granite_client is None:
            return None

        from backend.tikz.repair_prompts import TIKZ_REPAIR_SYSTEM_PROMPT

        user_msg = (
            f"The following LaTeX TikZ code failed to compile:\n\n"
            f"Error log:\n{error_log[-2000:]}\n\n"
            f"Broken code:\n```latex\n{tikz_code}\n```\n\n"
            "Fix the LaTeX syntax error and return the complete corrected code "
            "inside ```latex ... ``` blocks:"
        )
        import re
        raw = granite_client.chat(TIKZ_REPAIR_SYSTEM_PROMPT, user_msg)
        match = re.search(r"```(?:latex|tex)?\s*(.*?)```", raw, re.DOTALL)
        if match:
            return match.group(1).strip()
        if "\\documentclass" in raw:
            start = raw.find("\\documentclass")
            end = raw.rfind("\\end{document}") + len("\\end{document}")
            return raw[start:end].strip()
        return raw.strip()

    # ── Full pipeline ─────────────────────────────────────────────────────────

    def run_full(
        self,
        ir: DiagramIR,
        tikz_code: str,
        granite_client=None,
    ) -> tuple[ValidationReport, str]:
        """
        Run all validation stages.
        If compilation fails and a granite_client is supplied, attempt repairs.

        Returns (report, final_tikz_code).
        """
        report = ValidationReport()
        cfg = get_settings()
        max_repairs = cfg.max_repair_attempts

        # Stage 1-4: IR-level
        for stage_fn, kwargs in [
            (self.validate_semantic, {"ir": ir}),
            (self.validate_graph,    {"ir": ir}),
            (self.validate_geometry, {"ir": ir}),
            (self.validate_typography, {}),
        ]:
            result = stage_fn(**kwargs)
            report.stage_results[result.stage] = result
            if not result.passed:
                report.passed = False

        # Stage 5: Compilation with optional repair
        for attempt in range(max_repairs + 1):
            comp_result = self.validate_compilation(tikz_code)
            report.stage_results["compilation"] = comp_result
            if comp_result.passed:
                break
            report.passed = False
            if attempt < max_repairs and granite_client is not None:
                logger.info(
                    "Attempting TikZ repair %d/%d…", attempt + 1, max_repairs
                )
                repaired = self.repair_tikz(
                    tikz_code,
                    comp_result.errors[0] if comp_result.errors else "",
                    granite_client=granite_client,
                )
                if repaired:
                    tikz_code = repaired
                else:
                    break
            else:
                break

        return report, tikz_code
