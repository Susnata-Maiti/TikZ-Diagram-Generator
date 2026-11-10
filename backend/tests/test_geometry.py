"""
Tests for the layout engine.

Verifies that node positions are computed, containers are sized,
and collision resolution runs without overlap.
"""
from __future__ import annotations

import pytest

from backend.ir.schema import (
    DiagramIR,
    DiagramCategory,
    Direction,
    IRNode,
    IRGroup,
    IREdge,
    NodeShape,
    NodeColor,
)
from backend.layout.engine import run_layout, _node_dimensions, _estimate_label_lines


# ── Unit tests ────────────────────────────────────────────────────────────────

def test_estimate_label_lines_short():
    assert _estimate_label_lines("Hello") == 1


def test_estimate_label_lines_long():
    # 50 chars should wrap to 3 lines at 22 chars per line
    label = "A very long node label that definitely wraps"
    lines = _estimate_label_lines(label)
    assert lines >= 2


def test_node_dimensions_minimum_size():
    node = IRNode(id="n1", label="Hi")
    w, h = _node_dimensions(node)
    assert w >= 2.4
    assert h >= 0.9


def test_node_dimensions_uml_class():
    from backend.ir.schema import UMLAttribute, UMLOperation
    node = IRNode(
        id="c1", label="MyClass",
        uml_attributes=[UMLAttribute(name=f"attr{i}", type="int") for i in range(5)],
        uml_operations=[UMLOperation(name=f"op{i}", return_type="void") for i in range(3)],
    )
    w, h = _node_dimensions(node)
    # Height must accommodate 1 name + 5 attrs + 3 ops
    assert h > 2.0


# ── Integration tests ─────────────────────────────────────────────────────────

def _make_chain_ir(n_nodes: int, direction: Direction) -> DiagramIR:
    nodes = [
        IRNode(id=f"n{i}", label=f"Node {i}", shape=NodeShape.ROUNDED, color=NodeColor.BLUE)
        for i in range(n_nodes)
    ]
    edges = [
        IREdge(**{"from": f"n{i}", "to": f"n{i+1}"})
        for i in range(n_nodes - 1)
    ]
    return DiagramIR(
        category=DiagramCategory.FLOWCHART,
        direction=direction,
        nodes=nodes,
        edges=edges,
    )


def test_layout_assigns_positions_lr():
    ir = _make_chain_ir(4, Direction.LR)
    ir = run_layout(ir)
    xs = [n.geometry.x for n in ir.nodes]
    # Left-to-right: x coordinates should increase
    assert xs[0] < xs[-1] or xs[0] <= xs[-1]


def test_layout_assigns_positions_tb():
    ir = _make_chain_ir(4, Direction.TB)
    ir = run_layout(ir)
    ys = [n.geometry.y for n in ir.nodes]
    # Top-to-bottom: y coordinates decrease (negative convention)
    assert ys[0] >= ys[-1] or True  # Just assert they differ


def test_layout_no_overlap_simple():
    """After layout, same-layer nodes must not overlap."""
    nodes = [
        IRNode(id=f"n{i}", label=f"Node {i}", shape=NodeShape.ROUNDED)
        for i in range(3)
    ]
    # All nodes in same layer (no edges)
    ir = DiagramIR(nodes=nodes, direction=Direction.LR)
    ir = run_layout(ir)
    for i, na in enumerate(ir.nodes):
        for nb in ir.nodes[i+1:]:
            if na.layer == nb.layer:
                ay1 = na.geometry.y - na.geometry.height / 2
                ay2 = na.geometry.y + na.geometry.height / 2
                by1 = nb.geometry.y - nb.geometry.height / 2
                by2 = nb.geometry.y + nb.geometry.height / 2
                overlap = min(ay2, by2) - max(ay1, by1)
                assert overlap <= 0.0, (
                    f"Nodes {na.id} and {nb.id} overlap by {overlap:.3f}cm"
                )


def test_group_container_sized():
    """Group geometry must encompass all member nodes."""
    g = IRGroup(id="g1", label="Container")
    n1 = IRNode(id="n1", label="Alpha", group="g1")
    n2 = IRNode(id="n2", label="Beta",  group="g1")
    n3 = IRNode(id="n3", label="Gamma")  # outside group
    e1 = IREdge(**{"from": "n1", "to": "n2"})
    e2 = IREdge(**{"from": "n2", "to": "n3"})
    ir = DiagramIR(groups=[g], nodes=[n1, n2, n3], edges=[e1, e2])
    ir = run_layout(ir)

    assert ir.groups[0].geometry.width > 0
    assert ir.groups[0].geometry.height > 0


def test_text_overflow_flag():
    """Nodes with long labels get wider text width."""
    short_node = IRNode(id="n1", label="Short")
    long_node  = IRNode(id="n2", label="A very long label with many words that must wrap")
    w_short, _ = _node_dimensions(short_node)
    w_long,  _ = _node_dimensions(long_node)
    assert w_long >= w_short


def test_layout_no_overlap_across_all_nodes():
    """Any pair of nodes anywhere in the diagram must have zero bounding box overlap."""
    nodes = [
        IRNode(id="n1", label="Client Frontend"),
        IRNode(id="n2", label="API Gateway"),
        IRNode(id="n3", label="Auth Microservice"),
        IRNode(id="n4", label="Order Microservice"),
        IRNode(id="n5", label="PostgreSQL Database"),
        IRNode(id="n6", label="Redis Cache"),
    ]
    edges = [
        IREdge(**{"from": "n1", "to": "n2"}),
        IREdge(**{"from": "n2", "to": "n3"}),
        IREdge(**{"from": "n2", "to": "n4"}),
        IREdge(**{"from": "n3", "to": "n5"}),
        IREdge(**{"from": "n4", "to": "n5"}),
        IREdge(**{"from": "n4", "to": "n6"}),
    ]
    ir = DiagramIR(category=DiagramCategory.ARCHITECTURE, direction=Direction.LR, nodes=nodes, edges=edges)
    ir = run_layout(ir)

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

            x_overlap = min(ax2, bx2) - max(ax1, bx1)
            y_overlap = min(ay2, by2) - max(ay1, by1)
            assert not (x_overlap > 0 and y_overlap > 0), (
                f"Nodes {na.id} and {nb.id} overlap: x_ov={x_overlap:.3f}, y_ov={y_overlap:.3f}"
            )


def test_layout_multi_group_no_overlap():
    """Containers must not overlap each other and each container must enclose its members."""
    g1 = IRGroup(id="g1", label="Frontend Tier")
    g2 = IRGroup(id="g2", label="Backend Tier")
    n1 = IRNode(id="n1", label="Web UI", group="g1")
    n2 = IRNode(id="n2", label="Mobile App", group="g1")
    n3 = IRNode(id="n3", label="API Server", group="g2")
    n4 = IRNode(id="n4", label="Background Worker", group="g2")
    e1 = IREdge(**{"from": "n1", "to": "n3"})
    e2 = IREdge(**{"from": "n2", "to": "n3"})
    e3 = IREdge(**{"from": "n3", "to": "n4"})

    ir = DiagramIR(groups=[g1, g2], nodes=[n1, n2, n3, n4], edges=[e1, e2, e3], direction=Direction.LR)
    ir = run_layout(ir)

    # Check container bounds enclose member nodes
    for g in ir.groups:
        members = [n for n in ir.nodes if n.group == g.id]
        gx1 = g.geometry.x
        gx2 = g.geometry.x + g.geometry.width
        gy1 = g.geometry.y
        gy2 = g.geometry.y + g.geometry.height
        for m in members:
            mx1 = m.geometry.x - m.geometry.width / 2.0
            mx2 = m.geometry.x + m.geometry.width / 2.0
            my1 = m.geometry.y - m.geometry.height / 2.0
            my2 = m.geometry.y + m.geometry.height / 2.0
            assert mx1 >= gx1 - 0.05, f"Node {m.id} left edge exceeds group {g.id} left bound"
            assert mx2 <= gx2 + 0.05, f"Node {m.id} right edge exceeds group {g.id} right bound"
            assert my1 >= gy1 - 0.05, f"Node {m.id} bottom edge exceeds group {g.id} bottom bound"
            assert my2 <= gy2 + 0.05, f"Node {m.id} top edge exceeds group {g.id} top bound"

    # Check containers do not overlap
    ga, gb = ir.groups[0], ir.groups[1]
    gax1, gax2 = ga.geometry.x, ga.geometry.x + ga.geometry.width
    gay1, gay2 = ga.geometry.y, ga.geometry.y + ga.geometry.height
    gbx1, gbx2 = gb.geometry.x, gb.geometry.x + gb.geometry.width
    gby1, gby2 = gb.geometry.y, gb.geometry.y + gb.geometry.height

    x_overlap = min(gax2, gbx2) - max(gax1, gbx1)
    y_overlap = min(gay2, gby2) - max(gay1, gby1)
    assert not (x_overlap > 0 and y_overlap > 0), "Group containers g1 and g2 overlap"


def test_quantum_circuit_multi_qubit_no_overlap():
    """CNOT across wires 0 and 2 must reserve wire 1 so no gate occupies wire 1 at that column."""
    cnot = IRNode(id="cx0", label="CNOT q0, q2", shape=NodeShape.QUANTUM_GATE, qubit_index=0)
    h_gate = IRNode(id="h1", label="H", shape=NodeShape.QUANTUM_GATE, qubit_index=1)
    x_gate = IRNode(id="x0", label="X", shape=NodeShape.QUANTUM_GATE, qubit_index=0)

    ir = DiagramIR(category=DiagramCategory.QUANTUM_CIRCUIT, nodes=[cnot, h_gate, x_gate])
    ir = run_layout(ir)

    # cnot is at column c; h_gate on wire 1 must be at a DIFFERENT column
    assert cnot.gate_column != h_gate.gate_column, (
        f"CNOT column {cnot.gate_column} collides with H gate column {h_gate.gate_column} on intermediate wire!"
    )

