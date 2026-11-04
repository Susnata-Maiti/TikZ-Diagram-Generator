"""
TikZ Generation Agent.

Converts a validated, laid-out DiagramIR into a complete compilable LaTeX document.
Mimics Claude-style diagrams on its chat window:
- Colourful containers with distinct header pill badges and generous breathing room.
- Clear entity hierarchy with zero overlaps of containers, lines/arrows, and text.
- Clean modern sans-serif typography (Helvetica) with pill badges for edge labels.
- Authentic IBM Qiskit-style depiction for quantum circuits.
"""
from __future__ import annotations

import re
import logging
from typing import Any

from backend.ir.schema import (
    DiagramIR,
    IRNode,
    IREdge,
    IRGroup,
    NodeShape,
    NodeColor,
    EdgeRouting,
    EdgeStyle,
    EdgeArrow,
    Direction,
    DiagramCategory,
)
from backend.conventions.registry import get_registry
from backend.config import get_settings

logger = logging.getLogger(__name__)


# ── LaTeX escaping ────────────────────────────────────────────────────────────

_LATEX_SPECIAL = {
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "^": r"\^{}",
    "~": r"\textasciitilde{}",
    "<": r"\textless{}",
    ">": r"\textgreater{}",
    "|": r"\textbar{}",
    "→": r"$\rightarrow$",
    "←": r"$\leftarrow$",
    "↔": r"$\leftrightarrow$",
    "⇒": r"$\Rightarrow$",
    "⇐": r"$\Leftarrow$",
    "⇔": r"$\Leftrightarrow$",
    "•": r"$\bullet$",
    "±": r"$\pm$",
    "×": r"$\times$",
    "÷": r"$\div$",
    "≤": r"$\le$",
    "≥": r"$\ge$",
    "≠": r"$\ne$",
    "≈": r"$\approx$",
    "∞": r"$\infty$",
}


def escape_latex(text: str) -> str:
    if not text:
        return ""
    for k, v in _LATEX_SPECIAL.items():
        text = text.replace(k, v)
    return text


def _safe_id(raw: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_]", "", str(raw))


# ── Claude Color Palettes ─────────────────────────────────────────────────────

COLOR_PALETTE: dict[NodeColor, dict[str, str]] = {
    NodeColor.BLUE:   {"fill": "blue!7",    "draw": "blue!70!black",   "text": "blue!90!black"},
    NodeColor.GREEN:  {"fill": "teal!7",    "draw": "teal!70!black",   "text": "teal!90!black"},
    NodeColor.ORANGE: {"fill": "orange!9",  "draw": "orange!75!black", "text": "orange!95!black"},
    NodeColor.PURPLE: {"fill": "violet!7",  "draw": "violet!70!black", "text": "violet!90!black"},
    NodeColor.GRAY:   {"fill": "gray!7",    "draw": "gray!60!black",   "text": "black!85"},
    NodeColor.RED:    {"fill": "red!7",     "draw": "red!70!black",    "text": "red!90!black"},
    NodeColor.TEAL:   {"fill": "teal!8",    "draw": "teal!75!black",   "text": "teal!90!black"},
    NodeColor.YELLOW: {"fill": "yellow!14", "draw": "yellow!75!black", "text": "black!85"},
    NodeColor.WHITE:  {"fill": "white",     "draw": "gray!55!black",   "text": "black!85"},
    NodeColor.BLACK:  {"fill": "black!85",  "draw": "black",           "text": "white"},
}

CONTAINER_PALETTES: dict[str, dict[str, str]] = {
    "blue":   {"fill": "blue!5",   "draw": "blue!50!black",   "badge_bg": "blue!15",   "badge_txt": "blue!90!black",   "badge_border": "blue!40!black"},
    "purple": {"fill": "violet!5", "draw": "violet!50!black", "badge_bg": "violet!15", "badge_txt": "violet!90!black", "badge_border": "violet!40!black"},
    "teal":   {"fill": "teal!5",   "draw": "teal!55!black",   "badge_bg": "teal!15",   "badge_txt": "teal!90!black",   "badge_border": "teal!40!black"},
    "orange": {"fill": "orange!6", "draw": "orange!60!black", "badge_bg": "orange!18", "badge_txt": "orange!90!black", "badge_border": "orange!45!black"},
    "red":    {"fill": "red!5",    "draw": "red!50!black",    "badge_bg": "red!15",    "badge_txt": "red!90!black",    "badge_border": "red!40!black"},
    "green":  {"fill": "green!6",  "draw": "green!50!black",  "badge_bg": "green!18",  "badge_txt": "green!90!black",  "badge_border": "green!40!black"},
    "gray":   {"fill": "gray!6",   "draw": "gray!50!black",   "badge_bg": "gray!18",   "badge_txt": "gray!90!black",   "badge_border": "gray!40!black"},
}

CONTAINER_COLOR_CYCLE = ["blue", "purple", "teal", "orange", "red", "green"]


def _color_str(color: NodeColor) -> tuple[str, str]:
    palette = COLOR_PALETTE.get(color, COLOR_PALETTE[NodeColor.BLUE])
    return palette["fill"], palette["draw"]


# ── Arrow tip mapping ──────────────────────────────────────────────────────────

def _arrow_tip(arrow: EdgeArrow, is_head: bool) -> str:
    mapping = {
        EdgeArrow.NONE:           "",
        EdgeArrow.OPEN:           "Latex" if is_head else "",
        EdgeArrow.FILLED:         "Triangle[fill]" if is_head else "",
        EdgeArrow.HOLLOW:         "Triangle[open]" if is_head else "",
        EdgeArrow.DIAMOND_OPEN:   "Diamond[open]",
        EdgeArrow.DIAMOND_FILLED: "Diamond[fill]",
        EdgeArrow.CROW_ONE:       "Bar[]",
        EdgeArrow.CROW_MANY:      "Straight Barb[reversed]",
        EdgeArrow.CROW_ZERO_ONE:  "Circle[open] Bar[]",
        EdgeArrow.CROW_ONE_MANY:  "Bar[] Straight Barb[reversed]",
        EdgeArrow.CROW_ZERO_MANY: "Circle[open] Straight Barb[reversed]",
    }
    return mapping.get(arrow, "Latex" if is_head else "")


def _edge_arrow_spec(edge: IREdge) -> str:
    tail = _arrow_tip(edge.arrow_tail, is_head=False)
    head = _arrow_tip(edge.arrow_head, is_head=True)
    if tail and head:
        return f"{{{tail}}}-{{{head}}}"
    if head:
        return f"-{{{head}}}"
    if tail:
        return f"{{{tail}}}-"
    return "-"


# ── Shape style name lookup ───────────────────────────────────────────────────

_SHAPE_TO_STYLE: dict[NodeShape, str] = {
    NodeShape.RECTANGLE:    "gen_rect",
    NodeShape.ROUNDED:      "gen_round",
    NodeShape.DIAMOND:      "gen_diamond",
    NodeShape.CYLINDER:     "gen_cylinder",
    NodeShape.CIRCLE:       "gen_circle",
    NodeShape.ELLIPSE:      "gen_ellipse",
    NodeShape.PARALLELOGRAM: "gen_para",
    NodeShape.DOUBLE_RECT:  "gen_double_rect",
    NodeShape.ACTOR:        "gen_actor",
    NodeShape.CLOUD:        "gen_cloud",
    NodeShape.NOTE:         "gen_note",
    NodeShape.HEXAGON:      "gen_hexagon",
    NodeShape.TERMINATOR:   "fc_terminator",
    NodeShape.PROCESS:      "fc_process",
    NodeShape.DECISION:     "gen_diamond",
    NodeShape.IO_BOX:       "gen_para",
    NodeShape.DATA_STORE:   "gen_rect",
    NodeShape.QUANTUM_GATE: "qgate",
    NodeShape.MEASUREMENT:  "qmeasure",
}


# ── TikZ document builder ─────────────────────────────────────────────────────

class TikZGenerator:
    """Converts a fully laid-out DiagramIR to a standalone LaTeX/TikZ document."""

    def __init__(self) -> None:
        self.cfg = get_settings()
        self.registry = get_registry()

    def generate(self, ir: DiagramIR) -> str:
        # If it's a quantum circuit, use the dedicated IBM Qiskit generator
        if ir.category == DiagramCategory.QUANTUM_CIRCUIT:
            return self._generate_quantum_circuit(ir)

        profile = self.registry.get(ir.category)
        lines: list[str] = []

        lines += self._preamble(profile.tikz_libraries)
        lines += self._begin_tikzpicture(profile.tikz_styles)

        # Nodes
        for node in ir.nodes:
            lines += self._node_lines(node, ir)

        # Group containers (drawn in background layer with Claude aesthetics)
        if ir.groups:
            lines += self._group_lines(ir)

        # Edges
        for edge in ir.edges:
            lines += self._edge_lines(edge, ir)

        lines.append(r"\end{tikzpicture}")
        lines.append(r"\end{document}")
        return "\n".join(lines)

    # ── Preamble ──────────────────────────────────────────────────────────────

    def _preamble(self, extra_libraries: list[str]) -> list[str]:
        cfg = self.cfg
        libs = list(dict.fromkeys(
            ["positioning", "arrows.meta", "calc", "fit",
             "backgrounds", "shapes.geometric", "shapes.multipart",
             "shapes.symbols"] + extra_libraries
        ))
        lib_str = ", ".join(libs)

        lines = [
            r"\documentclass[tikz, border=18pt]{standalone}",
            r"\usepackage[T1]{fontenc}",
            r"\usepackage[scaled=0.92]{helvet}",
            r"\renewcommand{\familydefault}{\sfdefault}",
            r"\usepackage{tikz}",
            rf"\usetikzlibrary{{{lib_str}}}",
            r"\pgfkeys{/pgf/arrow keys/Crow/.tip={Straight Barb[reversed]}}",
            r"\begin{document}",
        ]
        return lines

    # ── Begin tikzpicture ────────────────────────────────────────────────────

    def _begin_tikzpicture(self, extra_styles: list[str]) -> list[str]:
        cfg = self.cfg
        base_styles = [
            rf"  every node/.style={{font=\sffamily\small}},",
            # Claude-style shapes: modern rounded corners, clean stroke, generous padding
            rf"  gen_rect/.style={{draw, line width=0.85pt, rectangle, rounded corners=6pt, text width=2.8cm, "
            rf"minimum height=1.1cm, align=center, inner sep=6pt}},",
            rf"  gen_round/.style={{draw, line width=0.85pt, rectangle, rounded corners=8pt, "
            rf"text width=2.8cm, minimum height=1.1cm, align=center, inner sep=6pt}},",
            rf"  gen_diamond/.style={{draw, line width=0.85pt, diamond, aspect=1.8, "
            rf"text width=2.0cm, align=center, inner sep=3pt}},",
            rf"  gen_cylinder/.style={{draw, line width=0.85pt, cylinder, shape border rotate=90, "
            rf"aspect=0.25, text width=2.2cm, minimum height=1.2cm, align=center, inner sep=5pt}},",
            rf"  gen_circle/.style={{draw, line width=0.85pt, circle, text width=1.6cm, "
            rf"align=center, inner sep=4pt}},",
            rf"  gen_ellipse/.style={{draw, line width=0.85pt, ellipse, text width=2.2cm, "
            rf"align=center, inner sep=4pt}},",
            rf"  gen_para/.style={{draw, line width=0.85pt, trapezium, trapezium left angle=80, "
            rf"trapezium right angle=100, text width=2.5cm, align=center, inner sep=4pt}},",
            rf"  gen_double_rect/.style={{draw, line width=0.85pt, double, rectangle, rounded corners=6pt, "
            rf"text width=2.8cm, minimum height=1.1cm, align=center, inner sep=6pt}},",
            rf"  gen_actor/.style={{draw=none, inner sep=2pt, align=center}},",
            rf"  gen_cloud/.style={{draw, line width=0.85pt, cloud, cloud puffs=9, "
            rf"text width=2.2cm, align=center, inner sep=4pt}},",
            rf"  gen_note/.style={{draw, line width=0.85pt, rectangle, rounded corners=4pt, "
            rf"text width=2.8cm, align=left, inner sep=6pt, fill=yellow!10, draw=yellow!70!black}},",
            rf"  gen_hexagon/.style={{draw, line width=0.85pt, regular polygon, regular polygon sides=6, "
            rf"text width=1.8cm, align=center, inner sep=3pt}},",
            rf"  fc_terminator/.style={{draw, line width=0.85pt, rounded corners=16pt, "
            rf"text width=2.5cm, minimum height=0.9cm, align=center, inner sep=5pt}},",
            rf"  fc_process/.style={{draw, line width=0.85pt, rectangle, rounded corners=5pt, "
            rf"text width=2.8cm, minimum height=1.0cm, align=center, inner sep=5pt}},",
            rf"  qgate/.style={{draw=teal!75!black, fill=teal!20, line width=0.9pt, rounded corners=2pt, "
            rf"minimum size=0.85cm, align=center, font=\sffamily\bfseries\small}},",
            rf"  qmeasure/.style={{draw=black!75, fill=gray!12, line width=0.9pt, rounded corners=2pt, "
            rf"minimum size=0.85cm, align=center}},",
            rf"  edge_label/.style={{fill=white, draw=gray!35, thin, inner sep=2.5pt, "
            rf"font=\sffamily\scriptsize, text=black!85, rounded corners=3pt}},",
            rf"  flow_arrow/.style={{->, line width=0.85pt, draw=black!75}},",
        ]
        extra = [f"  {s}," for s in extra_styles]

        return (
            [r"\begin{tikzpicture}[", "  >=Latex,"]
            + base_styles
            + extra
            + [r"]"]
        )

    # ── Node lines ────────────────────────────────────────────────────────────

    def _node_lines(self, node: IRNode, ir: DiagramIR) -> list[str]:
        """Generate \\node command(s) for one IR node."""
        n_id = _safe_id(node.id)
        shape_style = _SHAPE_TO_STYLE.get(node.shape, "gen_round")
        fill, draw_color = _color_str(node.color)

        w_cm = node.geometry.width
        h_cm = node.geometry.height
        x_cm = node.geometry.x
        y_cm = node.geometry.y

        if (ir.category == DiagramCategory.UML_CLASS
                and (node.uml_attributes or node.uml_operations)):
            return self._uml_class_node(node, n_id, fill, draw_color, w_cm, x_cm, y_cm)

        label_tex = escape_latex(node.label)
        if node.stereotype:
            label_tex = rf"\textit{{\tiny «{escape_latex(node.stereotype)}»}}\\{label_tex}"

        style_str = (
            f"{shape_style}, "
            f"fill={fill}, draw={draw_color}, "
            f"text width={w_cm:.2f}cm, "
            f"minimum height={h_cm:.2f}cm"
        )
        pos = f"at ({x_cm:.3f}cm, {y_cm:.3f}cm)"

        return [f"  \\node[{style_str}] ({n_id}) {pos} {{{label_tex}}};"]

    def _uml_class_node(
        self,
        node: IRNode,
        n_id: str,
        fill: str,
        draw_color: str,
        w_cm: float,
        x_cm: float,
        y_cm: float,
    ) -> list[str]:
        """Generate a rectangle split (multipart) UML class node."""
        label = escape_latex(node.label)
        stereo = (
            rf"\textit{{\tiny «{escape_latex(node.stereotype)}»}}\\ "
            if node.stereotype else ""
        )

        part1 = rf"{stereo}\textbf{{{label}}}"
        attr_lines = r" \\ ".join(
            escape_latex(a.to_latex()) for a in node.uml_attributes
        ) or r"\phantom{a}"
        op_lines = r" \\ ".join(
            escape_latex(o.to_latex()) for o in node.uml_operations
        ) or r"\phantom{a}"

        parts = (
            3 if node.uml_operations else
            (2 if node.uml_attributes else 1)
        )

        style_str = (
            f"draw={draw_color}, line width=0.85pt, fill={fill}, rounded corners=5pt, "
            f"rectangle split, rectangle split parts={parts}, "
            f"text width={w_cm:.2f}cm, align=left, inner sep=5pt, "
            f"font=\\sffamily\\small"
        )
        pos = f"at ({x_cm:.3f}cm, {y_cm:.3f}cm)"

        content = f"{part1} \\nodepart{{two}} {attr_lines}"
        if parts == 3:
            content += f" \\nodepart{{three}} {op_lines}"

        return [f"  \\node[{style_str}] ({n_id}) {pos} {{{content}}};"]

    # ── Group (container) lines - Claude Aesthetics ──────────────────────────

    def _group_lines(self, ir: DiagramIR) -> list[str]:
        """Draw group containers in the background layer with Claude aesthetic pill badges."""
        lines = [r"  \begin{pgfonlayer}{background}"]

        group_member_ids: dict[str, list[str]] = {}
        for node in ir.nodes:
            if node.group:
                group_member_ids.setdefault(node.group, []).append(_safe_id(node.id))

        cfg = get_settings()
        inner_sep = f"{cfg.layout_container_inner_sep_cm * 28.35:.0f}pt"

        for idx, group in enumerate(ir.groups):
            g_id = _safe_id(group.id)
            g_label = escape_latex(group.label)
            members = group_member_ids.get(group.id, [])
            if not members:
                continue

            member_str = " ".join(f"({m})" for m in members)

            # Pick container palette (cycling through vibrant pastels)
            color_key = group.color.value if hasattr(group.color, "value") else str(group.color).lower()
            if color_key not in CONTAINER_PALETTES or color_key == "gray":
                color_key = CONTAINER_COLOR_CYCLE[idx % len(CONTAINER_COLOR_CYCLE)]
            pal = CONTAINER_PALETTES.get(color_key, CONTAINER_PALETTES["blue"])

            line_style = "dashed" if group.style == "dashed" else "solid"

            box_style = (
                f"draw={pal['draw']}, fill={pal['fill']}, {line_style}, "
                f"line width=1.0pt, rounded corners=12pt, inner sep={inner_sep}"
            )
            badge_style = (
                f"fill={pal['badge_bg']}, draw={pal['badge_border']}, text={pal['badge_txt']}, "
                f"font=\\sffamily\\bfseries\\scriptsize, rounded corners=3.5pt, inner sep=3.5pt, "
                f"anchor=south west"
            )

            lines.append(
                f"    \\node[{box_style}, fit={member_str}] ({g_id}) {{}};"
            )
            lines.append(
                f"    \\node[{badge_style}] at ({g_id}.north west) {{ {g_label} }};"
            )

        lines.append(r"  \end{pgfonlayer}")
        return lines

    # ── Edge lines ────────────────────────────────────────────────────────────

    def _edge_lines(self, edge: IREdge, ir: DiagramIR) -> list[str]:
        u = _safe_id(edge.from_node)
        v = _safe_id(edge.to_node)
        if not u or not v:
            return []

        arrow_spec = _edge_arrow_spec(edge)
        line_style = "dashed" if edge.style == EdgeStyle.DASHED else (
            "dotted" if edge.style == EdgeStyle.DOTTED else ""
        )
        double = "double" if edge.style == EdgeStyle.DOUBLE else ""

        # Compose draw options with smooth rounded corners
        draw_opts_parts = [f"{arrow_spec}", "line width=0.85pt", "draw=black!75", "rounded corners=5pt"]
        if line_style:
            draw_opts_parts.append(line_style)
        if double:
            draw_opts_parts.append(double)
        draw_opts = ", ".join(filter(None, draw_opts_parts))

        label_tex = escape_latex(edge.label)
        label_node = f" node[midway, edge_label] {{{label_tex}}} " if label_tex else " "

        mult_head = escape_latex(edge.multiplicity_head)
        mult_tail = escape_latex(edge.multiplicity_tail)
        mult_near_end   = f" node[near end,   edge_label] {{{mult_head}}} " if mult_head else ""
        mult_near_start = f" node[near start, edge_label] {{{mult_tail}}} " if mult_tail else ""

        routing = edge.routing
        direction = ir.direction
        is_lr = direction == Direction.LR

        node_order = {n.id: i for i, n in enumerate(ir.nodes)}
        u_idx = node_order.get(edge.from_node, 0)
        v_idx = node_order.get(edge.to_node, 0)
        is_skip = abs(v_idx - u_idx) > 1
        is_back = v_idx < u_idx

        edge_label_part = label_node + mult_near_start + mult_near_end

        if routing == EdgeRouting.SELF_LOOP:
            return [
                f"  \\draw[{draw_opts}] ({u}.north east) to[out=30, in=-30, "
                f"looseness=3]{edge_label_part}({v}.south east);"
            ]

        if routing == EdgeRouting.CURVED or (is_back and routing == EdgeRouting.DIRECT):
            bend = edge.bend_angle if edge.bend_angle else (25 if is_back else 0)
            return [
                f"  \\draw[{draw_opts}] ({u}) to[bend left={bend}]{edge_label_part}({v});"
            ]

        if routing in (EdgeRouting.ORTHOGONAL_UP,) or (is_skip and not is_back):
            return [
                f"  \\draw[{draw_opts}] ({u}.north) -- ++(0,0.9cm) "
                f"-|{edge_label_part}({v}.north);"
            ]

        if routing == EdgeRouting.ORTHOGONAL_DOWN or (is_skip and is_back):
            return [
                f"  \\draw[{draw_opts}] ({u}.south) -- ++(0,-0.9cm) "
                f"-|{edge_label_part}({v}.south);"
            ]

        if routing == EdgeRouting.ORTHOGONAL:
            if is_lr:
                return [
                    f"  \\draw[{draw_opts}] ({u}.east) -|{edge_label_part}({v}.north);"
                ]
            else:
                return [
                    f"  \\draw[{draw_opts}] ({u}.south) |-{edge_label_part}({v}.west);"
                ]

        # Default: direct
        if is_lr:
            return [f"  \\draw[{draw_opts}] ({u}.east) --{edge_label_part}({v}.west);"]
        else:
            return [f"  \\draw[{draw_opts}] ({u}.south) --{edge_label_part}({v}.north);"]

    # ── Dedicated IBM Qiskit Quantum Circuit Generator ───────────────────────

    def _generate_quantum_circuit(self, ir: DiagramIR) -> str:
        """
        Generates an authentic IBM Qiskit-style quantum circuit diagram:
        - Parallel horizontal qubit wires: q0 : |0⟩, q1 : |0⟩, etc.
        - Classical register: double wire labeled 'c' at bottom if measurements present.
        - Qiskit-style gate square boxes (H, X, Y, Z, S, T, etc.).
        - CNOT: solid black dot on control wire, ⊕ on target wire, connected by a vertical line.
        - Measurement: meter box with needle + classical double feed line to register c.
        - Barriers: vertical dashed line across wires.
        """
        lines: list[str] = [
            r"\documentclass[tikz, border=16pt]{standalone}",
            r"\usepackage[T1]{fontenc}",
            r"\usepackage[scaled=0.92]{helvet}",
            r"\renewcommand{\familydefault}{\sfdefault}",
            r"\usepackage{tikz}",
            r"\usetikzlibrary{positioning, arrows.meta, calc}",
            r"\begin{document}",
            r"\begin{tikzpicture}[",
            r"  qwire/.style={line width=0.8pt, draw=black!75},",
            r"  cwire/.style={double, double distance=1.5pt, line width=0.5pt, draw=black!60},",
            r"  qgate_h/.style={draw=teal!80!black, fill=teal!22, line width=0.9pt, rounded corners=2pt, minimum size=0.85cm, align=center, font=\sffamily\bfseries\small},",
            r"  qgate_x/.style={draw=cyan!80!black, fill=cyan!22, line width=0.9pt, rounded corners=2pt, minimum size=0.85cm, align=center, font=\sffamily\bfseries\small},",
            r"  qgate_y/.style={draw=blue!80!black, fill=blue!20, line width=0.9pt, rounded corners=2pt, minimum size=0.85cm, align=center, font=\sffamily\bfseries\small},",
            r"  qgate_z/.style={draw=green!80!black, fill=green!20, line width=0.9pt, rounded corners=2pt, minimum size=0.85cm, align=center, font=\sffamily\bfseries\small},",
            r"  qgate_phase/.style={draw=violet!80!black, fill=violet!20, line width=0.9pt, rounded corners=2pt, minimum size=0.85cm, align=center, font=\sffamily\bfseries\small},",
            r"  qgate_generic/.style={draw=blue!80!black, fill=blue!18, line width=0.9pt, rounded corners=2pt, minimum size=0.85cm, align=center, font=\sffamily\bfseries\small},",
            r"  qcontrol/.style={circle, fill=black!85, inner sep=2.5pt},",
            r"  qtarget/.style={circle, draw=black!85, line width=1.0pt, inner sep=4.2pt},",
            r"  meter_box/.style={draw=black!75, fill=gray!12, line width=0.9pt, rounded corners=2pt, minimum size=0.85cm},",
            r"]",
        ]

        num_qubits = ir.properties.get("num_qubits", 2)
        wire_y_spacing = ir.properties.get("wire_y_spacing", 1.5)
        circuit_end_x = ir.properties.get("circuit_end_x", 6.5)
        has_measurement = ir.properties.get("has_measurement", False)

        # 1. Qubit wires
        for q in range(num_qubits):
            y_q = -q * wire_y_spacing
            lines.append(f"  \\draw[qwire] (-0.8, {y_q:.2f}) -- ({circuit_end_x:.2f}, {y_q:.2f});")
            lines.append(f"  \\node[left, font=\\sffamily\\small] at (-0.8, {y_q:.2f}) {{$q_{q} : |0\\rangle$}};")

        # 2. Classical register wire if measurements exist
        y_c = -num_qubits * wire_y_spacing - 0.2
        if has_measurement:
            lines.append(f"  \\draw[cwire] (-0.8, {y_c:.2f}) -- ({circuit_end_x:.2f}, {y_c:.2f});")
            lines.append(f"  \\node[left, font=\\sffamily\\small] at (-0.8, {y_c:.2f}) {{$c$}};")

        # 3. Draw gates
        drawn_cnot_ids: set[str] = set()
        meas_idx = 0

        for node in ir.nodes:
            if node.id in drawn_cnot_ids:
                continue

            nid = _safe_id(node.id)
            lbl = node.label.strip()
            lbl_lower = lbl.lower()
            x = node.geometry.x
            y = node.geometry.y
            q = node.qubit_index if node.qubit_index is not None else 0

            # CNOT / CX gate
            if "cnot" in lbl_lower or "cx" in lbl_lower:
                drawn_cnot_ids.add(node.id)
                ctrl_q = q
                matches = [int(m) for m in re.findall(r"q(\d+)", lbl, re.IGNORECASE)]
                if len(matches) >= 2:
                    ctrl_q = matches[0]
                    tgt_q = matches[1]
                elif len(matches) == 1 and matches[0] != ctrl_q:
                    tgt_q = matches[0]
                else:
                    tgt_q = None
                    for e in ir.edges:
                        if e.from_node == node.id:
                            dst = next((n for n in ir.nodes if n.id == e.to_node), None)
                            if dst and dst.qubit_index is not None and dst.qubit_index != ctrl_q:
                                tgt_q = dst.qubit_index
                                break
                    if tgt_q is None:
                        tgt_q = (ctrl_q + 1) % num_qubits

                cy_ctrl = -ctrl_q * wire_y_spacing
                cy_tgt = -tgt_q * wire_y_spacing

                lines.append(f"  % CNOT: control q{ctrl_q} -> target q{tgt_q}")
                lines.append(f"  \\node[qcontrol] ({nid}_ctrl) at ({x:.3f}, {cy_ctrl:.3f}) {{}};")
                lines.append(f"  \\node[qtarget] ({nid}_tgt) at ({x:.3f}, {cy_tgt:.3f}) {{}};")
                lines.append(f"  \\draw[line width=1.1pt, draw=black!85] ({nid}_ctrl) -- ({nid}_tgt);")
                lines.append(f"  \\draw[line width=1.0pt, draw=black!85] ({x:.3f}, {cy_tgt:.3f}-4.2pt) -- ({x:.3f}, {cy_tgt:.3f}+4.2pt);")
                lines.append(f"  \\draw[line width=1.0pt, draw=black!85] ({x:.3f}-4.2pt, {cy_tgt:.3f}) -- ({x:.3f}+4.2pt, {cy_tgt:.3f});")
                continue

            # Measurement gate
            if node.shape == NodeShape.MEASUREMENT or "measure" in lbl_lower:
                lines.append(f"  % Measurement: {node.id} on q{q}")
                lines.append(f"  \\node[meter_box] ({nid}) at ({x:.3f}, {y:.3f}) {{}};")
                lines.append(f"  \\draw[line width=0.8pt, draw=black!80] ({x:.3f}-0.22, {y:.3f}-0.12) arc (160:20:0.24);")
                lines.append(f"  \\draw[-{{Latex[scale=0.7]}}, line width=0.8pt, draw=black!80] ({x:.3f}-0.05, {y:.3f}-0.12) -- ({x:.3f}+0.18, {y:.3f}+0.16);")
                if has_measurement:
                    lines.append(f"  \\draw[-{{Latex[scale=0.75]}}, cwire] ({nid}.south) -- ({x:.3f}, {y_c:.2f});")
                    lines.append(f"  \\node[right, font=\\sffamily\\tiny, text=black!70] at ({x:.3f}, {y_c - 0.25:.2f}) {{{meas_idx}}};")
                    meas_idx += 1
                continue

            # Barrier
            if "barrier" in lbl_lower:
                top_y = 0.5
                bottom_y = -num_qubits * wire_y_spacing + 0.5
                lines.append(f"  \\draw[dashed, gray!70, line width=1pt] ({x:.3f}, {top_y:.2f}) -- ({x:.3f}, {bottom_y:.2f});")
                continue

            # Single Qubit Gates (H, X, Y, Z, S, T, etc.)
            gate_name = "H"
            style_name = "qgate_generic"

            if "hadamard" in lbl_lower or lbl == "H":
                gate_name = "H"
                style_name = "qgate_h"
            elif lbl_lower in ("x", "not", "pauli-x"):
                gate_name = "X"
                style_name = "qgate_x"
            elif lbl_lower in ("y", "pauli-y"):
                gate_name = "Y"
                style_name = "qgate_y"
            elif lbl_lower in ("z", "pauli-z"):
                gate_name = "Z"
                style_name = "qgate_z"
            elif lbl_lower in ("s", "t", "rx", "ry", "rz", "phase"):
                gate_name = lbl.upper()
                style_name = "qgate_phase"
            else:
                # Extract short label
                words = lbl.split()
                gate_name = words[0][:4] if words else "U"

            lines.append(f"  \\node[{style_name}] ({nid}) at ({x:.3f}, {y:.3f}) {{{gate_name}}};")

        lines.append(r"\end{tikzpicture}")
        lines.append(r"\end{document}")
        return "\n".join(lines)
