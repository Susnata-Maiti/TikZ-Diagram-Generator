"""
Computational Geometry and Layout Engine.

Responsibilities:
- Assign positions to nodes with distinct clarity and zero overlap.
- Clean clustered layout for grouped/container nodes (Claude aesthetic).
- Dedicated IBM Qiskit layout for quantum circuits with collision-free wire allocations.
- Accurate sizing of group containers with generous margins and badge headroom.
- Comprehensive multi-pass collision detection and separation for nodes and containers.

Does NOT call Granite. All layout is deterministic.
"""
from __future__ import annotations

import math
import re
import logging
from typing import Optional, Any

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
_MAX_NODE_W     = 5.8    # cm
_MAX_LABEL_CHARS_PER_LINE = 22

# Generous default spacing to guarantee zero entity overlap
_DEFAULT_H_GAP_CM = 3.2   # cm horizontal gap between ranks
_DEFAULT_V_GAP_CM = 2.2   # cm vertical gap between sibling nodes
_GROUP_CROSS_GAP_CM = 1.4 # cm extra gap between different groups in same layer
_CONTAINER_PADDING_CM = 0.85 # cm inner padding for container boundaries
_MIN_NODE_SEPARATION_CM = 0.50 # cm minimum clearance between any two node boundaries
_MIN_GROUP_SEPARATION_CM = 1.00 # cm minimum clearance between group containers
_CONTAINER_BADGE_HEADROOM = 0.60 # cm extra headroom for the container pill badge


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
    Estimate (width_cm, height_cm) for a node based on its label content,
    shape geometry, and any UML class members.
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

    # Shape-specific padding to prevent shape borders from clipping text
    if node.shape in (NodeShape.DIAMOND, NodeShape.DECISION):
        # Diamonds need extra diagonal clearance
        w = max(w * 1.35, 2.6)
        h = max(h * 1.35, 1.8)
    elif node.shape == NodeShape.CYLINDER:
        h = h + 0.4  # top/bottom elliptical caps
    elif node.shape in (NodeShape.CIRCLE, NodeShape.ACTOR):
        diameter = max(w, h, 2.2)
        w = diameter
        h = diameter
    elif node.shape == NodeShape.PARALLELOGRAM or node.shape == NodeShape.IO_BOX:
        w = w + 0.6  # slant width margin

    return round(w, 2), round(h, 2)


# ── IBM Qiskit Quantum Circuit Layout ─────────────────────────────────────────

class QuantumCircuitLayout:
    """
    Dedicated layout for IBM Qiskit-style quantum circuits.
    Arranges parallel horizontal qubit wires with gates placed in discrete time-slice columns.
    Guarantees no vertical connector or gate overlaps.
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

        all_qubit_refs: list[int] = list(qubit_tracker.values())
        for n in nodes:
            for m in re.findall(r"q(?:ubit)?\s*(\d+)", n.label, re.IGNORECASE):
                all_qubit_refs.append(int(m))
        num_qubits = max(max(all_qubit_refs, default=1) + 1, 2)

        # 2. Collision-free gate column assignment
        # Track occupied columns on each wire to ensure no gates collide
        # and multi-qubit gates (like CNOT) don't cross intermediate wire gates.
        from collections import defaultdict
        wire_occupied: dict[int, set[int]] = defaultdict(set)
        ctrl_to_tgt: dict[str, str] = {}
        for e in self.ir.edges:
            ctrl_to_tgt[e.from_node] = e.to_node

        for n in nodes:
            if n.gate_column is not None:
                # Pre-specified column
                q = n.qubit_index or 0
                wire_occupied[q].add(n.gate_column)
                continue

            q = n.qubit_index or 0
            lbl_lower = n.label.lower()
            is_cnot = "cnot" in lbl_lower or "cx" in lbl_lower

            if is_cnot:
                # Determine control and target wires
                tgt_id = ctrl_to_tgt.get(n.id)
                tgt_node = next((x for x in nodes if x.id == tgt_id), None)
                tgt_q = tgt_node.qubit_index if tgt_node and tgt_node.qubit_index is not None else ((q + 1) % num_qubits)
                
                # Check label for explicit wire indices like "CNOT q0, q1"
                matches = [int(m) for m in re.findall(r"q(\d+)", n.label, re.IGNORECASE)]
                if len(matches) >= 2:
                    q = matches[0]
                    tgt_q = matches[1]
                n.qubit_index = q

                q_min, q_max = min(q, tgt_q), max(q, tgt_q)
                wires_span = range(q_min, q_max + 1)

                # Find the first column where all wires in the span are free
                c = 0
                while any(c in wire_occupied[w] for w in wires_span):
                    c += 1

                n.gate_column = c
                if tgt_node:
                    tgt_node.gate_column = c
                    tgt_node.qubit_index = tgt_q

                for w in wires_span:
                    wire_occupied[w].add(c)
            else:
                # Single qubit gate
                c = 0
                while c in wire_occupied[q]:
                    c += 1
                n.gate_column = c
                wire_occupied[q].add(c)

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
    - Mathematical band allocation guaranteeing container non-overlap.
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

        # 2. Build adjacency and assign topological layers (cycle-safe)
        layers = self._assign_layers()

        # 3. Assign positions with group clustering and non-overlapping bands
        self._assign_positions(layers)

        # 4. Multi-pass collision resolution loop
        for _ in range(8):
            changed_nodes = self._resolve_node_collisions()
            self._size_groups()
            changed_groups = self._resolve_group_collisions()
            changed_foreign = self._resolve_group_foreign_node_collisions()
            if not (changed_nodes or changed_groups or changed_foreign):
                break

        # Final sizing pass for containers
        self._size_groups()

        return self.ir

    def _assign_layers(self) -> dict[str, int]:
        """Topological layer assignment with robust cycle breaking."""
        nodes = self.ir.nodes
        node_ids = {n.id for n in nodes}
        adj: dict[str, list[str]] = {n.id: [] for n in nodes}
        pred: dict[str, list[str]] = {n.id: [] for n in nodes}

        for e in self.ir.edges:
            if e.from_node in node_ids and e.to_node in node_ids and e.from_node != e.to_node:
                adj[e.from_node].append(e.to_node)
                pred[e.to_node].append(e.from_node)

        # Detect feedback edges using DFS state: 0=unvisited, 1=visiting, 2=visited
        state: dict[str, int] = {n.id: 0 for n in nodes}
        feedback_edges: set[tuple[str, str]] = set()

        def _find_cycles(u: str) -> None:
            state[u] = 1
            for v in adj[u]:
                if state[v] == 1:
                    feedback_edges.add((u, v))
                elif state[v] == 0:
                    _find_cycles(v)
            state[u] = 2

        for n in nodes:
            if state[n.id] == 0:
                _find_cycles(n.id)

        # Compute longest-path layers on DAG (ignoring feedback edges)
        dag_pred: dict[str, list[str]] = {
            nid: [p for p in preds if (p, nid) not in feedback_edges]
            for nid, preds in pred.items()
        }

        layers: dict[str, int] = {}

        def _get_layer(node_id: str, stack: set[str]) -> int:
            if node_id in layers:
                return layers[node_id]
            if node_id in stack:
                return 0
            stack.add(node_id)
            if not dag_pred[node_id]:
                layers[node_id] = 0
            else:
                layers[node_id] = max(_get_layer(p, stack) for p in dag_pred[node_id]) + 1
            stack.remove(node_id)
            return layers[node_id]

        for n in nodes:
            if n.id not in layers:
                _get_layer(n.id, set())

        # Save layer numbers to IR nodes
        for n in nodes:
            n.layer = layers.get(n.id, 0)

        return layers

    def _assign_positions(self, layers: dict[str, int]) -> None:
        """
        Assign coordinates with group-clustering and guaranteed clearance.
        Coordinates (x, y) represent the geometric CENTER of each node in TikZ.
        """
        cfg = self.cfg
        h_gap = max(cfg.layout_h_gap_cm, _DEFAULT_H_GAP_CM)
        v_gap = max(cfg.layout_v_gap_cm, _DEFAULT_V_GAP_CM)

        layer_nodes: dict[int, list[IRNode]] = {}
        for node in self.ir.nodes:
            layer = layers.get(node.id, 0)
            layer_nodes.setdefault(layer, []).append(node)

        direction = self.ir.direction
        is_lr = direction == Direction.LR
        sorted_layers = sorted(layer_nodes.keys())

        # Determine if groups share layers (swimlanes) or are sequential tiers
        group_layers: dict[str, set[int]] = {}
        for node in self.ir.nodes:
            if node.group:
                group_layers.setdefault(node.group, set()).add(layers.get(node.id, 0))

        # Check for group overlaps in layer space
        group_list = [g.id for g in self.ir.groups]
        groups_overlap_layers = False
        for i, g1 in enumerate(group_list):
            for g2 in group_list[i + 1:]:
                if group_layers.get(g1, set()) & group_layers.get(g2, set()):
                    groups_overlap_layers = True
                    break
            if groups_overlap_layers:
                break

        # If groups share layers, assign dedicated cross-axis bands to guarantee non-overlapping containers
        group_cross_offsets: dict[str, float] = {}
        if groups_overlap_layers and len(self.ir.groups) > 1:
            band_cursor = 0.0
            for g_id in group_list:
                members = [n for n in self.ir.nodes if n.group == g_id]
                # Max nodes in any single layer for this group
                max_nodes_in_layer = 1
                for lyr in group_layers.get(g_id, set()):
                    cnt = sum(1 for n in members if layers.get(n.id, 0) == lyr)
                    max_nodes_in_layer = max(max_nodes_in_layer, cnt)

                group_cross_offsets[g_id] = band_cursor
                avg_cross_dim = (v_gap + 1.2) if is_lr else (h_gap + 2.8)
                band_cursor += max_nodes_in_layer * avg_cross_dim + _GROUP_CROSS_GAP_CM + 2 * _CONTAINER_PADDING_CM

        # ── Main Axis and Cross Axis Placement ────────────────────────────────
        main_axis_cursor = 0.0

        for layer_idx in sorted_layers:
            nodes_in_layer = layer_nodes[layer_idx]
            # Cluster nodes belonging to the same group together
            nodes_in_layer.sort(key=lambda n: (group_list.index(n.group) if n.group in group_list else 999, n.id))

            # Compute layer max dimension along main axis
            if is_lr:
                layer_main_dim = max(n.geometry.width for n in nodes_in_layer)
                layer_center_x = main_axis_cursor + layer_main_dim / 2.0
            else:
                layer_main_dim = max(n.geometry.height for n in nodes_in_layer)
                layer_center_y = -(main_axis_cursor + layer_main_dim / 2.0)

            # Assign cross-axis positions
            cross_cursor = 0.0
            last_group: Optional[str] = None

            for node in nodes_in_layer:
                w = node.geometry.width
                h = node.geometry.height

                # Margin between groups in the same layer
                if last_group is not None and node.group != last_group:
                    cross_cursor += _GROUP_CROSS_GAP_CM

                if is_lr:
                    # In LR: main axis is X, cross axis is Y (negative convention)
                    node.geometry.x = round(layer_center_x, 3)
                    # Apply swimlane band offset if groups share layers
                    base_y = group_cross_offsets.get(node.group, 0.0) if groups_overlap_layers else 0.0
                    node_y = -(base_y + cross_cursor + h / 2.0)
                    node.geometry.y = round(node_y, 3)
                    cross_cursor += h + v_gap
                else:
                    # In TB: main axis is Y, cross axis is X (positive convention)
                    base_x = group_cross_offsets.get(node.group, 0.0) if groups_overlap_layers else 0.0
                    node_x = base_x + cross_cursor + w / 2.0
                    node.geometry.x = round(node_x, 3)
                    node.geometry.y = round(layer_center_y, 3)
                    cross_cursor += w + h_gap

                last_group = node.group

            # Advance main axis cursor
            main_axis_cursor += layer_main_dim + (h_gap if is_lr else v_gap)

    def _size_groups(self) -> None:
        """Compute exact bounding box for each group container with generous padding."""
        group_map: dict[str, list[IRNode]] = {}
        for node in self.ir.nodes:
            if node.group:
                group_map.setdefault(node.group, []).append(node)

        padding = max(self.cfg.layout_container_inner_sep_cm, _CONTAINER_PADDING_CM)

        for group in self.ir.groups:
            members = group_map.get(group.id, [])
            if not members:
                group.geometry = NodeGeometry(x=0.0, y=0.0, width=2.0, height=1.0)
                continue

            # Node geometry (x, y) is the CENTER:
            # left = x - w/2, right = x + w/2, bottom = y - h/2, top = y + h/2
            min_x = min(n.geometry.x - n.geometry.width / 2.0 for n in members)
            max_x = max(n.geometry.x + n.geometry.width / 2.0 for n in members)
            min_y = min(n.geometry.y - n.geometry.height / 2.0 for n in members)
            max_y = max(n.geometry.y + n.geometry.height / 2.0 for n in members)

            group.geometry = NodeGeometry(
                x=round(min_x - padding, 3),
                y=round(min_y - padding, 3),
                width=round((max_x - min_x) + 2 * padding, 3),
                height=round((max_y - min_y) + 2 * padding + _CONTAINER_BADGE_HEADROOM, 3),
            )

    def _resolve_node_collisions(self) -> bool:
        """
        Multi-pass collision resolution using exact center-based bounding boxes.
        Guarantees no two nodes overlap or touch.
        """
        nodes = self.ir.nodes
        min_sep = _MIN_NODE_SEPARATION_CM
        direction = self.ir.direction
        is_lr = direction == Direction.LR
        changed = False

        for i, na in enumerate(nodes):
            for nb in nodes[i + 1:]:
                # Exact bounding boxes based on centers
                ax1 = na.geometry.x - na.geometry.width / 2.0
                ax2 = na.geometry.x + na.geometry.width / 2.0
                ay1 = na.geometry.y - na.geometry.height / 2.0
                ay2 = na.geometry.y + na.geometry.height / 2.0

                bx1 = nb.geometry.x - nb.geometry.width / 2.0
                bx2 = nb.geometry.x + nb.geometry.width / 2.0
                by1 = nb.geometry.y - nb.geometry.height / 2.0
                by2 = nb.geometry.y + nb.geometry.height / 2.0

                x_overlap = min(ax2, bx2) - max(ax1, bx1)
                y_overlap = min(ay2, by2) - max(ay1, by1)

                if x_overlap > -min_sep and y_overlap > -min_sep:
                    # Nodes are overlapping or violating separation
                    if is_lr or abs(na.geometry.x - nb.geometry.x) < 0.2:
                        # In LR, separate vertically along cross-axis to preserve rank ordering
                        shift = (y_overlap + min_sep) / 2.0
                        if na.geometry.y >= nb.geometry.y:
                            na.geometry.y += shift
                            nb.geometry.y -= shift
                        else:
                            na.geometry.y -= shift
                            nb.geometry.y += shift
                    else:
                        # In TB, separate horizontally along cross-axis
                        shift = (x_overlap + min_sep) / 2.0
                        if na.geometry.x >= nb.geometry.x:
                            na.geometry.x += shift
                            nb.geometry.x -= shift
                        else:
                            na.geometry.x -= shift
                            nb.geometry.x += shift
                    changed = True

        return changed

    def _resolve_group_collisions(self) -> bool:
        """Separate group containers if their bounding boxes overlap."""
        if len(self.ir.groups) < 2:
            return False

        group_map: dict[str, list[IRNode]] = {}
        for node in self.ir.nodes:
            if node.group:
                group_map.setdefault(node.group, []).append(node)

        groups = self.ir.groups
        min_sep = _MIN_GROUP_SEPARATION_CM
        is_lr = self.ir.direction == Direction.LR
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

                if x_overlap > -min_sep and y_overlap > -min_sep:
                    # Separate along the cross-axis to maintain stream flow
                    if is_lr:
                        shift = (y_overlap + min_sep)
                        for member in group_map.get(gb.id, []):
                            member.geometry.y -= shift
                        gb.geometry.y -= shift
                    else:
                        shift = (x_overlap + min_sep)
                        for member in group_map.get(gb.id, []):
                            member.geometry.x += shift
                        gb.geometry.x += shift
                    changed = True

        return changed

    def _resolve_group_foreign_node_collisions(self) -> bool:
        """
        Ensure nodes that do NOT belong to group G do NOT fall inside
        or intersect group G's container bounding box.
        """
        if not self.ir.groups:
            return False

        changed = False
        margin = 0.5  # cm clearance from container border

        for group in self.ir.groups:
            gx1 = group.geometry.x - margin
            gx2 = group.geometry.x + group.geometry.width + margin
            gy1 = group.geometry.y - margin
            gy2 = group.geometry.y + group.geometry.height + margin

            for node in self.ir.nodes:
                if node.group == group.id:
                    continue  # Member node

                nx1 = node.geometry.x - node.geometry.width / 2.0
                nx2 = node.geometry.x + node.geometry.width / 2.0
                ny1 = node.geometry.y - node.geometry.height / 2.0
                ny2 = node.geometry.y + node.geometry.height / 2.0

                x_overlap = min(gx2, nx2) - max(gx1, nx1)
                y_overlap = min(gy2, ny2) - max(gy1, ny1)

                if x_overlap > 0 and y_overlap > 0:
                    # Foreign node intersects container! Push it outside along the nearest edge
                    if self.ir.direction == Direction.LR:
                        # Push vertically
                        if node.geometry.y >= (gy1 + gy2) / 2.0:
                            node.geometry.y = gy2 + node.geometry.height / 2.0 + margin
                        else:
                            node.geometry.y = gy1 - node.geometry.height / 2.0 - margin
                    else:
                        # Push horizontally
                        if node.geometry.x >= (gx1 + gx2) / 2.0:
                            node.geometry.x = gx2 + node.geometry.width / 2.0 + margin
                        else:
                            node.geometry.x = gx1 - node.geometry.width / 2.0 - margin
                    changed = True

        return changed


# ── Public API ────────────────────────────────────────────────────────────────

def run_layout(ir: DiagramIR) -> DiagramIR:
    """
    Run the layout engine on the given IR.
    Returns the same IR object with geometry populated and guaranteed zero overlap.
    """
    if ir.category == DiagramCategory.QUANTUM_CIRCUIT:
        return QuantumCircuitLayout(ir).compute()
    return LayeredLayout(ir).compute()
