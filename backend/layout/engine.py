"""
Computational Geometry and Layout Engine.

Responsibilities:
- Assign positions to nodes with distinct clarity and zero overlap.
- Clean clustered layout for grouped/container nodes (Claude aesthetic).
- Dedicated IBM Qiskit layout for quantum circuits.
- Sizing of group containers with generous margins.
- Collision detection and separation pass for nodes and containers.

Does NOT call Granite. All layout is deterministic.
"""
from __future__ import annotations

import math
import re
import logging
from typing import Optional

from backend.config import get_settings
from backend.ir.schema import (
    DiagramIR,
    Direction,
    IRNode,
    IRGroup,
    NodeGeometry,
    DiagramCategory,
    NodeShape,
)

logger = logging.getLogger(__name__)

# ── Spacing and typography constants ──────────────────────────────────────────

_CHAR_WIDTH_CM  = 0.20   # cm per character (helvet/sans-serif ~10pt)
_LINE_HEIGHT_CM = 0.58   # cm per text line
_MIN_NODE_W     = 2.6    # cm
_MIN_NODE_H     = 1.1    # cm
_MAX_NODE_W     = 5.6    # cm
_MAX_LABEL_CHARS_PER_LINE = 22

# Generous default spacing to prevent any overlapping
_DEFAULT_H_GAP_CM = 3.2   # cm horizontal gap between ranks
_DEFAULT_V_GAP_CM = 2.2   # cm vertical gap between sibling nodes
_GROUP_CROSS_GAP_CM = 1.0 # cm extra gap between different groups in same layer
_CONTAINER_PADDING_CM = 0.85 # cm inner padding for container boundaries


# ── Text dimension helpers ────────────────────────────────────────────────────

def _estimate_label_lines(label: str, max_chars: int = _MAX_LABEL_CHARS_PER_LINE) -> int:
    """Return how many wrapped lines a label requires."""
    if not label:
        return 1
    paragraphs = label.split("\\\\")
    total_lines = 0
    for para in paragraphs:
        words = para.split()
        if not words:
            total_lines += 1
            continue
        lines = 1
        current = 0
        for word in words:
            if current + len(word) + 1 <= max_chars:
                current += len(word) + 1
            else:
                lines += 1
                current = len(word)
        total_lines += lines
    return max(1, total_lines)


def _node_dimensions(
    node: IRNode,
    extra_lines: int = 0,
    cfg=None,
) -> tuple[float, float]:
    """
    Estimate (width_cm, height_cm) for a node based on its label content
    and any UML class members.
    """
    if cfg is None:
        cfg = get_settings()

    label_lines = _estimate_label_lines(node.label)
    uml_attr_lines = len(node.uml_attributes)
    uml_op_lines   = len(node.uml_operations)

    text_segments = [seg.strip() for seg in node.label.replace("\\\\", "\n").splitlines()]
    widest_chars = max(
        (len(s) for s in text_segments),
        default=len(node.label)
    )
    if node.uml_attributes:
        widest_chars = max(widest_chars, *(len(a.to_latex()) for a in node.uml_attributes))
    if node.uml_operations:
        widest_chars = max(widest_chars, *(len(o.to_latex()) for o in node.uml_operations))

    w = max(_MIN_NODE_W, min(_MAX_NODE_W, min(widest_chars, _MAX_LABEL_CHARS_PER_LINE) * _CHAR_WIDTH_CM + 1.0))
    h_content = (
        label_lines * _LINE_HEIGHT_CM
        + uml_attr_lines * _LINE_HEIGHT_CM
        + uml_op_lines   * _LINE_HEIGHT_CM
        + extra_lines    * _LINE_HEIGHT_CM
    )
    h = max(_MIN_NODE_H, h_content + 0.6)

    if node.stereotype:
        h += _LINE_HEIGHT_CM

    return round(w, 2), round(h, 2)


# ── IBM Qiskit Quantum Circuit Layout ─────────────────────────────────────────

class QuantumCircuitLayout:
    """
    Dedicated layout for IBM Qiskit-style quantum circuits.
    Arranges parallel horizontal qubit wires with gates placed in discrete time-slice columns.
    """

    def __init__(self, ir: DiagramIR, cfg=None) -> None:
        self.ir = ir
        self.cfg = cfg or get_settings()

    def compute(self) -> DiagramIR:
        nodes = self.ir.nodes
        if not nodes:
            return self.ir

        # 1. Deduce qubit indices
        qubit_tracker: dict[str, int] = {}
        for n in nodes:
            if n.qubit_index is not None:
                qubit_tracker[n.id] = int(n.qubit_index)
            else:
                match = re.search(r"q(?:ubit)?\s*(\d+)", n.label, re.IGNORECASE)
                if match:
                    qubit_tracker[n.id] = int(match.group(1))

        # Check edges for qubit hints
        for e in self.ir.edges:
            if e.from_node in qubit_tracker and e.to_node not in qubit_tracker:
                qubit_tracker[e.to_node] = (qubit_tracker[e.from_node] + 1) % 4
            elif e.to_node in qubit_tracker and e.from_node not in qubit_tracker:
                qubit_tracker[e.from_node] = max(0, qubit_tracker[e.to_node] - 1)

        unassigned = [n for n in nodes if n.id not in qubit_tracker]
        for i, n in enumerate(unassigned):
            qubit_tracker[n.id] = i % 2

        for n in nodes:
            n.qubit_index = qubit_tracker[n.id]

        num_qubits = max(max(qubit_tracker.values(), default=1) + 1, 2)

        # 2. Deduce / assign gate columns
        wire_col_tracker: dict[int, int] = {q: 0 for q in range(num_qubits)}
        ctrl_to_tgt: dict[str, str] = {}
        for e in self.ir.edges:
            ctrl_to_tgt[e.from_node] = e.to_node

        for n in nodes:
            if n.gate_column is not None:
                continue

            q = n.qubit_index
            if n.id in ctrl_to_tgt:
                tgt_id = ctrl_to_tgt[n.id]
                tgt_node = next((x for x in nodes if x.id == tgt_id), None)
                if tgt_node:
                    tgt_q = tgt_node.qubit_index or 0
                    c = max(wire_col_tracker[q], wire_col_tracker[tgt_q])
                    n.gate_column = c
                    tgt_node.gate_column = c
                    wire_col_tracker[q] = c + 1
                    wire_col_tracker[tgt_q] = c + 1
                    continue

            c = wire_col_tracker[q]
            n.gate_column = c
            wire_col_tracker[q] = c + 1

        # 3. Geometry coordinates
        x_start = 1.4        # cm offset for wire labels on the left
        col_width = 1.6      # cm spacing between gate columns
        wire_y_spacing = 1.5 # cm spacing between qubit wires
        gate_size = 0.85     # cm standard square gate box

        max_col = max((n.gate_column for n in nodes if n.gate_column is not None), default=1)

        for n in nodes:
            col = n.gate_column if n.gate_column is not None else 0
            q = n.qubit_index if n.qubit_index is not None else 0
            x = x_start + col * col_width
            y = -q * wire_y_spacing
            n.geometry = NodeGeometry(x=round(x, 3), y=round(y, 3), width=gate_size, height=gate_size)

        has_meas = any(
            n.shape == NodeShape.MEASUREMENT or "measure" in n.label.lower()
            for n in nodes
        )
        circuit_end_x = x_start + (max_col + 1) * col_width + 0.8
        if not hasattr(self.ir, "properties") or self.ir.properties is None:
            self.ir.properties = {}
        self.ir.properties["num_qubits"] = num_qubits
        self.ir.properties["has_measurement"] = has_meas
        self.ir.properties["circuit_end_x"] = round(circuit_end_x, 3)
        self.ir.properties["wire_y_spacing"] = wire_y_spacing
        self.ir.properties["x_start"] = x_start

        return self.ir


# ── Layered & Clustered Layout (Claude Aesthetic) ────────────────────────────

class LayeredLayout:
    """
    Enhanced Coffman-Graham inspired layered layout.
    Features:
    - Generous spacing preventing overlapping of nodes, edges, or text.
    - Group-clustered layout keeping container nodes together.
    - Multi-pass collision detection and separation for nodes and containers.
    """

    def __init__(self, ir: DiagramIR, cfg=None) -> None:
        self.ir = ir
        self.cfg = cfg or get_settings()

    def compute(self) -> DiagramIR:
        nodes = self.ir.nodes
        if not nodes:
            return self.ir

        # 1. Assign dimensions to all nodes
        for node in nodes:
            w, h = _node_dimensions(node, cfg=self.cfg)
            node.geometry = NodeGeometry(x=0.0, y=0.0, width=w, height=h)

        # 2. Build adjacency for layering
        layers = self._assign_layers()

        # 3. Assign positions with group clustering
        self._assign_positions(layers)

        # 4. Collision resolution for nodes
        self._resolve_node_collisions()

        # 5. Size containers and resolve container-container collisions
        self._size_groups()
        self._resolve_group_collisions()

        return self.ir

    def _assign_layers(self) -> dict[str, int]:
        """Topological layer assignment with cycle handling."""
        adj: dict[str, list[str]] = {n.id: [] for n in self.ir.nodes}
        pred: dict[str, list[str]] = {n.id: [] for n in self.ir.nodes}
        for e in self.ir.edges:
            if e.from_node in adj and e.to_node in adj:
                adj[e.from_node].append(e.to_node)
                pred[e.to_node].append(e.from_node)

        layers: dict[str, int] = {}
        visited: set[str] = set()

        def _dfs(node_id: str) -> int:
            if node_id in layers:
                return layers[node_id]
            if node_id in visited:
                return 0
            visited.add(node_id)
            if not pred[node_id]:
                layers[node_id] = 0
            else:
                layers[node_id] = max(_dfs(p) for p in pred[node_id]) + 1
            return layers[node_id]

        for n in self.ir.nodes:
            if n.id not in layers:
                _dfs(n.id)

        return layers

    def _assign_positions(self, layers: dict[str, int]) -> None:
        """Assign coordinates with group-clustering and generous spacing."""
        cfg = self.cfg
        h_gap = max(cfg.layout_h_gap_cm, _DEFAULT_H_GAP_CM)
        v_gap = max(cfg.layout_v_gap_cm, _DEFAULT_V_GAP_CM)

        layer_nodes: dict[int, list[IRNode]] = {}
        for node in self.ir.nodes:
            layer = layers.get(node.id, 0)
            node.layer = layer
            layer_nodes.setdefault(layer, []).append(node)

        direction = self.ir.direction
        is_lr = direction == Direction.LR

        sorted_layers = sorted(layer_nodes.keys())

        main_axis_cursor = 0.0
        for layer_idx in sorted_layers:
            nodes_in_layer = layer_nodes[layer_idx]
            # Group clustering: cluster nodes belonging to the same group together
            nodes_in_layer.sort(key=lambda n: (n.group or "zzz_nogroup", n.id))

            cross_axis_cursor = 0.0
            last_group: Optional[str] = None
            for node in nodes_in_layer:
                w = node.geometry.width
                h = node.geometry.height

                # If switching to a new group, add an extra margin
                if last_group is not None and node.group != last_group:
                    cross_axis_cursor += _GROUP_CROSS_GAP_CM

                if is_lr:
                    node.geometry.x = main_axis_cursor
                    node.geometry.y = -(cross_axis_cursor + h / 2)
                    cross_axis_cursor += h + v_gap
                else:
                    node.geometry.x = cross_axis_cursor
                    node.geometry.y = -(main_axis_cursor + h / 2)
                    cross_axis_cursor += w + h_gap

                last_group = node.group

            # Advance main axis
            if is_lr:
                layer_w = max(n.geometry.width for n in nodes_in_layer)
                main_axis_cursor += layer_w + h_gap
            else:
                layer_h = max(n.geometry.height for n in nodes_in_layer)
                main_axis_cursor += layer_h + v_gap

    def _size_groups(self) -> None:
        """Compute bounding box for each group container with generous padding."""
        group_map: dict[str, list[IRNode]] = {}
        for node in self.ir.nodes:
            if node.group:
                group_map.setdefault(node.group, []).append(node)

        padding = max(self.cfg.layout_container_inner_sep_cm, _CONTAINER_PADDING_CM)
        for group in self.ir.groups:
            members = group_map.get(group.id, [])
            if not members:
                group.geometry = NodeGeometry(x=0, y=0, width=2.0, height=1.0)
                continue

            min_x = min(n.geometry.x for n in members)
            min_y = min(n.geometry.y - n.geometry.height / 2 for n in members)
            max_x = max(n.geometry.x + n.geometry.width for n in members)
            max_y = max(n.geometry.y + n.geometry.height / 2 for n in members)

            group.geometry = NodeGeometry(
                x=round(min_x - padding, 3),
                y=round(min_y - padding, 3),
                width=round((max_x - min_x) + 2 * padding, 3),
                height=round((max_y - min_y) + 2 * padding + 0.4, 3), # extra headroom for badge
            )

    def _resolve_node_collisions(self) -> None:
        """Multi-pass collision resolution to guarantee no overlapping nodes."""
        nodes = self.ir.nodes
        min_separation = 0.5  # cm

        for _ in range(12):
            changed = False
            for i, na in enumerate(nodes):
                for nb in nodes[i + 1:]:
                    # Check bounding box intersection
                    ax1 = na.geometry.x
                    ax2 = na.geometry.x + na.geometry.width
                    ay1 = na.geometry.y - na.geometry.height / 2
                    ay2 = na.geometry.y + na.geometry.height / 2

                    bx1 = nb.geometry.x
                    bx2 = nb.geometry.x + nb.geometry.width
                    by1 = nb.geometry.y - nb.geometry.height / 2
                    by2 = nb.geometry.y + nb.geometry.height / 2

                    x_overlap = min(ax2, bx2) - max(ax1, bx1)
                    y_overlap = min(ay2, by2) - max(ay1, by1)

                    if x_overlap > -min_separation and y_overlap > -min_separation:
                        # Shift along the smaller overlap dimension
                        if y_overlap > 0:
                            shift = (y_overlap + min_separation) / 2
                            if na.geometry.y >= nb.geometry.y:
                                na.geometry.y += shift
                                nb.geometry.y -= shift
                            else:
                                na.geometry.y -= shift
                                nb.geometry.y += shift
                            changed = True
                        elif x_overlap > 0:
                            shift = (x_overlap + min_separation) / 2
                            if na.geometry.x >= nb.geometry.x:
                                na.geometry.x += shift
                                nb.geometry.x -= shift
                            else:
                                na.geometry.x -= shift
                                nb.geometry.x += shift
                            changed = True
            if not changed:
                break

    def _resolve_group_collisions(self) -> None:
        """Separate containers if their bounding boxes overlap."""
        if len(self.ir.groups) < 2:
            return

        group_map: dict[str, list[IRNode]] = {}
        for node in self.ir.nodes:
            if node.group:
                group_map.setdefault(node.group, []).append(node)

        groups = self.ir.groups
        min_sep = 0.8  # cm separation between containers

        for _ in range(6):
            changed = False
            for i, ga in enumerate(groups):
                for gb in groups[i + 1:]:
                    gax1 = ga.geometry.x
                    gax2 = ga.geometry.x + ga.geometry.width
                    gay1 = ga.geometry.y
                    gay2 = ga.geometry.y + ga.geometry.height

                    gbx1 = gb.geometry.x
                    gbx2 = gb.geometry.x + gb.geometry.width
                    gby1 = gb.geometry.y
                    gby2 = gb.geometry.y + gb.geometry.height

                    x_overlap = min(gax2, gbx2) - max(gax1, gbx1)
                    y_overlap = min(gay2, gby2) - max(gay1, gby1)

                    if x_overlap > 0 and y_overlap > 0:
                        # Shift group B and all its members
                        shift = y_overlap + min_sep
                        for member in group_map.get(gb.id, []):
                            member.geometry.y -= shift
                        gb.geometry.y -= shift
                        changed = True
            if not changed:
                break


# ── Public API ────────────────────────────────────────────────────────────────

def run_layout(ir: DiagramIR) -> DiagramIR:
    """
    Run the layout engine on the given IR.
    Returns the same IR object with geometry populated.
    """
    if ir.category == DiagramCategory.QUANTUM_CIRCUIT:
        return QuantumCircuitLayout(ir).compute()
    return LayeredLayout(ir).compute()
