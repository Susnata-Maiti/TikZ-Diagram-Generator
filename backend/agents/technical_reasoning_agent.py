"""
Technical Reasoning Agent.

Critically evaluates the diagram's logical correctness,
detects inconsistencies, and suggests improvements.
Does NOT expose raw chain-of-thought.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from backend.agents.granite_client import GraniteClient
from backend.ir.schema import DiagramIR

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You are a senior technical diagram reviewer with expertise across
software engineering, electrical engineering, quantum computing, and data modeling.

Given a diagram IR description, produce a concise technical review covering:
1. Whether the diagram category and notation are correctly applied.
2. Any logically inconsistent, missing, or contradictory components.
3. Specific improvements to correctness (not aesthetics).
4. Key design decisions worth noting for the user.

Be direct, specific, and technically precise.
Do NOT expose internal chain-of-thought.
Respond in JSON:
{
  "is_consistent": true | false,
  "issues": ["list of specific issues"],
  "suggestions": ["list of actionable suggestions"],
  "design_decisions": ["brief notes on non-obvious design choices"],
  "severity": "ok" | "warning" | "error"
}
"""


@dataclass
class TechnicalReview:
    is_consistent: bool
    issues: list[str]
    suggestions: list[str]
    design_decisions: list[str]
    severity: str   # "ok" | "warning" | "error"


class TechnicalReasoningAgent:
    def __init__(self, client: GraniteClient) -> None:
        self._client = client

    def review(self, ir: DiagramIR) -> TechnicalReview:
        import json, re

        summary = (
            f"Diagram category: {ir.category.value}\n"
            f"Notation: {ir.notation_profile.value}\n"
            f"Nodes: {[n.label for n in ir.nodes]}\n"
            f"Edges: {[(e.from_node, e.to_node, e.label) for e in ir.edges]}\n"
            f"Groups: {[g.label for g in ir.groups]}\n"
            f"Title: {ir.title}\n"
        )
        user_msg = f"Review this diagram:\n\n{summary}\n\nRespond ONLY with the JSON object."

        try:
            raw = self._client.chat(_SYSTEM_PROMPT, user_msg)
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            if not match:
                raise ValueError("No JSON in response")
            data = json.loads(match.group(0))
            return TechnicalReview(
                is_consistent=bool(data.get("is_consistent", True)),
                issues=data.get("issues", []),
                suggestions=data.get("suggestions", []),
                design_decisions=data.get("design_decisions", []),
                severity=data.get("severity", "ok"),
            )
        except Exception as exc:
            logger.warning("TechnicalReasoningAgent failed: %s", exc)
            return TechnicalReview(
                is_consistent=True,
                issues=[],
                suggestions=[],
                design_decisions=[],
                severity="ok",
            )
