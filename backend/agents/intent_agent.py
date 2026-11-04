"""
Intent Understanding Agent.

Responsibilities:
- Parse the natural-language description.
- Identify diagram category and notation profile.
- Extract nodes, groups, and relationships.
- Produce a validated DiagramIR.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from backend.agents.granite_client import GraniteClient
from backend.ir.schema import (
    DiagramIR,
    DiagramCategory,
    NotationProfile,
    Direction,
    NodeShape,
    NodeColor,
    EdgeRouting,
    EdgeStyle,
    EdgeArrow,
    IRNode,
    IRGroup,
    IREdge,
)

logger = logging.getLogger(__name__)

# ── System prompt ─────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = r"""You are a precise scientific diagram architect and diagramming expert.

Your task: convert the user's natural-language description into a structured JSON Intermediate Representation (IR) for a technical diagram.

Return ONLY valid JSON matching this EXACT schema (no prose, no markdown fences around the outer object):
{
  "category": "<category>",
  "notation_profile": "<profile>",
  "direction": "LR" | "TB",
  "title": "<short diagram title>",
  "groups": [
    {"id": "g1", "label": "Container Title", "color": "gray", "style": "dashed"}
  ],
  "nodes": [
    {
      "id": "n1",
      "label": "Clear Concise Node Label",
      "shape": "<shape>",
      "group": "g1" | null,
      "color": "<color>",
      "stereotype": null | "<<interface>>",
      "uml_attributes": [],
      "uml_operations": [],
      "qubit_index": null,
      "gate_column": null,
      "properties": {}
    }
  ],
  "edges": [
    {
      "from": "n1",
      "to": "n2",
      "label": "Short edge label or empty string",
      "routing": "direct" | "orthogonal_up" | "orthogonal_down" | "orthogonal" | "curved",
      "style": "solid" | "dashed" | "dotted" | "double",
      "arrow_tail": "none" | "open" | "filled" | "hollow" | "diamond_open" | "diamond_filled" | "crow_one" | "crow_many" | "crow_zero_one" | "crow_one_many" | "crow_zero_many",
      "arrow_head": "none" | "open" | "filled" | "hollow" | "diamond_open" | "diamond_filled" | "crow_one" | "crow_many" | "crow_zero_one" | "crow_one_many" | "crow_zero_many",
      "multiplicity_tail": "",
      "multiplicity_head": ""
    }
  ],
  "agent_summary": "1-sentence explanation of what was generated."
}

Category values (pick the best match):
uml_class | uml_object | uml_use_case | uml_sequence | uml_activity | uml_state |
uml_component | uml_deployment | uml_package | flowchart | dfd | bpmn | workflow |
resource_allocation | erd | db_schema | architecture | network | cloud | microservices |
electrical | digital_logic | quantum_circuit | block_diagram | neural_network |
ml_pipeline | fsm | decision_tree | graph | signal_flow | generic

Notation profile values:
uml_2x | bpmn_2_0 | chen_erd | crows_foot | yourdon_dfd | gane_sarson | ieee_circuit | quantum_std | default

Shape values:
rectangle | rounded | diamond | cylinder | circle | ellipse | parallelogram | double_rect |
actor | cloud | note | hexagon | terminator | process | decision | io_box | data_store |
quantum_gate | measurement

Color values: blue | green | orange | purple | gray | red | teal | yellow | white | black

CRITICAL RULES:
1. Assign unique alphanumeric IDs: n1, n2, n3 … for nodes; g1, g2 … for groups.
2. Keep node labels concise, clean and legible (1-5 words per node, under 40 chars). Keep edge labels under 25 chars.
3. For architectures, microservices, cloud, networks, pipelines, and workflows: organize components into logical containers/groups (e.g. "Frontend Tier", "API Gateway", "Core Services", "Database Layer") and assign distinct vibrant colors ("blue", "purple", "teal", "orange", "red", "green"). Assign every related node to its group id!
4. For quantum circuits: set category to "quantum_circuit". Set qubit_index (0-based wire: 0 for q0, 1 for q1, ...) and gate_column (0-based time slice: 0, 1, 2, ...). Use standard gate names: "H", "X", "Y", "Z", "S", "T", "CNOT", "Measurement", "Barrier". For CNOT/CX: create control on qubit_index, target on target qubit_index, same gate_column, and add an edge from control to target.
5. For UML class diagrams, populate uml_attributes and uml_operations arrays.
6. For flowcharts: terminators for start/end, process rectangles, diamond decisions, io_box for I/O.
7. For ERDs: use the specified notation (chen_erd or crows_foot) and mark relationship types.
8. For electrical/digital circuits: use shape "rectangle" with stereotype for component type.
9. Use "orthogonal_up"/"orthogonal_down" only for skip-connections or feedback loops.
10. Return ONLY the JSON object.
"""

_REFINE_SYSTEM_PROMPT = r"""You are an intelligent Graph State Agent for a TikZ diagram generator.

Given the CURRENT JSON IR and a user refinement command, return the UPDATED JSON IR.

You may:
- Add, remove, rename, or reorder nodes and groups.
- Change node shapes, colors, stereotypes, attributes, or operations.
- Add, remove, or relabel edges; change routing/style/arrows.
- Change overall layout direction (LR / TB).
- Change category or notation_profile.

Return ONLY the complete updated JSON object matching the schema used at generation time.
Include "agent_summary": "1-sentence description of what changed."
"""

_ROUTER_SYSTEM_PROMPT = r"""Classify the user's diagram command into exactly one category:
1. UPDATE_IR   – Add/remove/rename nodes, edges, containers, change shapes/colors/direction.
2. STYLE_TIKZ  – Low-level LaTeX/TikZ styling not in the IR schema (line thickness, font size in pt, custom spacing).
3. NEW_DIAGRAM – Scrap current diagram and generate a completely new topic from scratch.

Respond with ONLY one word: UPDATE_IR, STYLE_TIKZ, or NEW_DIAGRAM.
"""


# ── Helper ────────────────────────────────────────────────────────────────────

def _extract_json(raw: str) -> dict[str, Any]:
    """Extract the first JSON object from model output (handles fenced blocks)."""
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if fenced:
        return json.loads(fenced.group(1))
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        raise ValueError(f"No JSON found in model output:\n{raw[:500]}")
    return json.loads(match.group(0))


def _sanitize_id(raw: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_]", "", str(raw))


# ── Agent ─────────────────────────────────────────────────────────────────────

class IntentAgent:
    """
    Converts natural-language prompts into a validated DiagramIR.
    Uses IBM Granite for semantic understanding.
    """

    def __init__(self, client: GraniteClient) -> None:
        self._client = client

    # ── Public API ────────────────────────────────────────────────────────────

    def generate_ir(self, description: str) -> DiagramIR:
        """Parse a natural-language description into a DiagramIR."""
        user_msg = (
            f"Diagram description:\n{description}\n\n"
            "Respond ONLY with the valid JSON object:"
        )
        raw = self._client.chat(_SYSTEM_PROMPT, user_msg)
        data = _extract_json(raw)
        return self._dict_to_ir(data, source_prompt=description)

    def refine_ir(self, current_ir: DiagramIR, instruction: str) -> DiagramIR:
        """Apply a natural-language refinement to an existing DiagramIR."""
        user_msg = (
            f"Current JSON IR:\n```json\n{json.dumps(current_ir.to_dict(), indent=2)}\n```\n\n"
            f"User refinement command: {instruction}\n\n"
            "Return ONLY the updated JSON object:"
        )
        raw = self._client.chat(_REFINE_SYSTEM_PROMPT, user_msg)
        data = _extract_json(raw)
        updated = self._dict_to_ir(data, source_prompt=instruction)
        # Preserve the original diagram ID so history links correctly
        updated.id = current_ir.id
        return updated

    def route_command(self, instruction: str) -> str:
        """Returns 'UPDATE_IR', 'STYLE_TIKZ', or 'NEW_DIAGRAM'."""
        raw = self._client.chat(
            _ROUTER_SYSTEM_PROMPT,
            f"User command: {instruction}",
        )
        for keyword in ("UPDATE_IR", "STYLE_TIKZ", "NEW_DIAGRAM"):
            if keyword in raw.upper():
                return keyword
        return "UPDATE_IR"

    # ── Internal helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _dict_to_ir(data: dict[str, Any], source_prompt: str = "") -> DiagramIR:
        """Convert raw model JSON dict to a DiagramIR, applying safe defaults."""

        category_raw = data.get("category", "generic")
        try:
            category = DiagramCategory(category_raw)
        except ValueError:
            category = DiagramCategory.GENERIC

        notation_raw = data.get("notation_profile", "default")
        try:
            notation = NotationProfile(notation_raw)
        except ValueError:
            notation = NotationProfile.DEFAULT

        direction_raw = data.get("direction", "LR").upper()
        try:
            direction = Direction(direction_raw)
        except ValueError:
            direction = Direction.LR

        # --- Groups ---
        groups: list[IRGroup] = []
        for g in data.get("groups", []):
            try:
                color = NodeColor(g.get("color", "gray"))
            except ValueError:
                color = NodeColor.GRAY
            groups.append(
                IRGroup(
                    id=_sanitize_id(g.get("id", f"g{len(groups)+1}")),
                    label=str(g.get("label", "Group"))[:60],
                    color=color,
                    style=g.get("style", "dashed"),
                )
            )

        # --- Nodes ---
        nodes: list[IRNode] = []
        for n in data.get("nodes", []):
            try:
                shape = NodeShape(n.get("shape", "rounded"))
            except ValueError:
                shape = NodeShape.ROUNDED
            try:
                color = NodeColor(n.get("color", "blue"))
            except ValueError:
                color = NodeColor.BLUE

            node = IRNode(
                id=_sanitize_id(n.get("id", f"n{len(nodes)+1}")),
                label=str(n.get("label", "Node"))[:80],
                shape=shape,
                color=color,
                group=_sanitize_id(n["group"]) if n.get("group") else None,
                stereotype=n.get("stereotype"),
                qubit_index=n.get("qubit_index"),
                gate_column=n.get("gate_column"),
                properties=n.get("properties", {}),
            )
            # UML class members
            from backend.ir.schema import UMLAttribute, UMLOperation
            for attr in n.get("uml_attributes", []):
                if isinstance(attr, dict):
                    node.uml_attributes.append(UMLAttribute(**attr))
                elif isinstance(attr, str) and attr.strip():
                    # LLM returned a plain string like "+ name : str"
                    node.uml_attributes.append(UMLAttribute(name=attr.strip()))
            for op in n.get("uml_operations", []):
                if isinstance(op, dict):
                    node.uml_operations.append(UMLOperation(**op))
                elif isinstance(op, str) and op.strip():
                    # LLM returned a plain string like "+ getName() : str"
                    node.uml_operations.append(UMLOperation(name=op.strip()))
            nodes.append(node)

        # --- Edges ---
        edges: list[IREdge] = []
        for e in data.get("edges", []):
            try:
                routing = EdgeRouting(e.get("routing", "direct"))
            except ValueError:
                routing = EdgeRouting.DIRECT
            try:
                style = EdgeStyle(e.get("style", "solid"))
            except ValueError:
                style = EdgeStyle.SOLID
            try:
                arrow_head = EdgeArrow(e.get("arrow_head", "open"))
            except ValueError:
                arrow_head = EdgeArrow.OPEN
            try:
                arrow_tail = EdgeArrow(e.get("arrow_tail", "none"))
            except ValueError:
                arrow_tail = EdgeArrow.NONE

            edges.append(
                IREdge(**{
                    "from": _sanitize_id(str(e.get("from", ""))),
                    "to":   _sanitize_id(str(e.get("to", ""))),
                    "label": str(e.get("label", ""))[:40],
                    "routing": routing,
                    "style": style,
                    "arrow_head": arrow_head,
                    "arrow_tail": arrow_tail,
                    "multiplicity_tail": str(e.get("multiplicity_tail", "")),
                    "multiplicity_head": str(e.get("multiplicity_head", "")),
                    "bend_angle": int(e.get("bend_angle", 0)),
                })
            )

        return DiagramIR(
            category=category,
            notation_profile=notation,
            direction=direction,
            title=str(data.get("title", ""))[:120],
            groups=groups,
            nodes=nodes,
            edges=edges,
            agent_summary=str(data.get("agent_summary", "")),
            source_prompt=source_prompt,
        )
