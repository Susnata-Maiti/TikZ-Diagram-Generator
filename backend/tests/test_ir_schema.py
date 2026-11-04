"""
Tests for the JSON Intermediate Representation schema.

Verifies Pydantic validation, edge reference checking,
and IR round-trip serialization.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.ir.schema import (
    DiagramIR,
    DiagramCategory,
    Direction,
    IRNode,
    IRGroup,
    IREdge,
    NodeShape,
    NodeColor,
    EdgeRouting,
    EdgeStyle,
    EdgeArrow,
    UMLAttribute,
    UMLOperation,
)


def _make_minimal_ir() -> DiagramIR:
    n1 = IRNode(id="n1", label="Start", shape=NodeShape.TERMINATOR, color=NodeColor.GREEN)
    n2 = IRNode(id="n2", label="Process", shape=NodeShape.PROCESS, color=NodeColor.BLUE)
    e1 = IREdge(**{"from": "n1", "to": "n2", "label": "begin"})
    return DiagramIR(
        category=DiagramCategory.FLOWCHART,
        direction=Direction.TB,
        nodes=[n1, n2],
        edges=[e1],
    )


def test_ir_creates_valid_object():
    ir = _make_minimal_ir()
    assert len(ir.nodes) == 2
    assert len(ir.edges) == 1


def test_ir_edge_alias_from_to():
    e = IREdge(**{"from": "n1", "to": "n2"})
    assert e.from_node == "n1"
    assert e.to_node == "n2"


def test_ir_edge_warns_on_missing_node():
    n1 = IRNode(id="n1", label="A")
    e = IREdge(**{"from": "n1", "to": "NONEXISTENT"})
    ir = DiagramIR(nodes=[n1], edges=[e])
    # The validator should add a warning
    assert any("NONEXISTENT" in w for w in ir.validation.warnings)


def test_ir_round_trip():
    ir = _make_minimal_ir()
    data = ir.to_dict()
    restored = DiagramIR.from_dict(data)
    assert restored.category == ir.category
    assert len(restored.nodes) == len(ir.nodes)
    assert len(restored.edges) == len(ir.edges)


def test_uml_attribute_to_latex():
    attr = UMLAttribute(visibility="+", name="count", type="int", default="0")
    s = attr.to_latex()
    assert "count" in s
    assert "int" in s
    assert "0" in s


def test_uml_operation_to_latex():
    op = UMLOperation(visibility="-", name="compute", params="x: float", return_type="float")
    s = op.to_latex()
    assert "compute" in s
    assert "float" in s


def test_ir_label_truncated():
    long_label = "A" * 200
    n = IRNode(id="n1", label=long_label)
    assert len(n.label) <= 80


def test_ir_edge_label_truncated():
    long_label = "X" * 100
    e = IREdge(**{"from": "a", "to": "b", "label": long_label})
    assert len(e.label) <= 40


def test_uml_class_ir_has_members():
    attrs = [UMLAttribute(name="x", type="int")]
    ops   = [UMLOperation(name="foo", return_type="void")]
    node  = IRNode(
        id="c1", label="MyClass",
        shape=NodeShape.RECTANGLE,
        uml_attributes=attrs,
        uml_operations=ops,
    )
    ir = DiagramIR(
        category=DiagramCategory.UML_CLASS,
        nodes=[node],
    )
    assert ir.nodes[0].uml_attributes[0].name == "x"
    assert ir.nodes[0].uml_operations[0].name == "foo"


def test_quantum_circuit_ir_qubit_index():
    gate = IRNode(
        id="h0", label="H", shape=NodeShape.QUANTUM_GATE,
        qubit_index=0, gate_column=0,
    )
    ir = DiagramIR(category=DiagramCategory.QUANTUM_CIRCUIT, nodes=[gate])
    assert ir.nodes[0].qubit_index == 0
