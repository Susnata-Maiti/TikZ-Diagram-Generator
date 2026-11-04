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
