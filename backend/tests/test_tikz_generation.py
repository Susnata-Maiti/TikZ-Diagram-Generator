"""
Tests for the TikZ code generator.

Verifies that the generated LaTeX is structurally correct
for several diagram categories without requiring Granite.
"""
from __future__ import annotations

import pytest

from backend.ir.schema import (
    DiagramIR, DiagramCategory, Direction,
    IRNode, IRGroup, IREdge,
    NodeShape, NodeColor, EdgeStyle, EdgeArrow,
    UMLAttribute, UMLOperation,
)
from backend.layout.engine import run_layout
from backend.tikz.generator import TikZGenerator, escape_latex


# ── Escape tests ──────────────────────────────────────────────────────────────

def test_escape_ampersand():
    assert r"\&" in escape_latex("A & B")


def test_escape_percent():
    assert r"\%" in escape_latex("50% complete")


def test_escape_underscore():
    assert r"\_" in escape_latex("some_id")


def test_escape_empty_string():
    assert escape_latex("") == ""


# ── Generic generation ────────────────────────────────────────────────────────

def _gen(ir: DiagramIR) -> str:
    ir = run_layout(ir)
    return TikZGenerator().generate(ir)


def test_output_contains_documentclass():
    ir = DiagramIR(nodes=[IRNode(id="n1", label="Test")])
    tikz = _gen(ir)
    assert "\\documentclass" in tikz


def test_output_contains_begin_tikzpicture():
    ir = DiagramIR(nodes=[IRNode(id="n1", label="Test")])
    tikz = _gen(ir)
    assert "\\begin{tikzpicture}" in tikz


def test_output_contains_end_document():
    ir = DiagramIR(nodes=[IRNode(id="n1", label="Test")])
    tikz = _gen(ir)
    assert "\\end{document}" in tikz


def test_node_id_in_output():
    ir = DiagramIR(nodes=[IRNode(id="mynode", label="MyNode")])
    tikz = _gen(ir)
    assert "(mynode)" in tikz


def test_edge_in_output():
    n1 = IRNode(id="n1", label="A")
    n2 = IRNode(id="n2", label="B")
    e  = IREdge(**{"from": "n1", "to": "n2", "label": "flows"})
    ir = DiagramIR(nodes=[n1, n2], edges=[e])
    tikz = _gen(ir)
    assert "n1" in tikz and "n2" in tikz


def test_group_background_layer():
    g  = IRGroup(id="g1", label="MyGroup")
    n1 = IRNode(id="n1", label="Inside", group="g1")
    n2 = IRNode(id="n2", label="Inside2", group="g1")
    ir = DiagramIR(groups=[g], nodes=[n1, n2])
    tikz = _gen(ir)
    assert "pgfonlayer" in tikz
    assert "g1" in tikz


# ── UML Class Diagram ─────────────────────────────────────────────────────────

def test_uml_class_multipart_node():
    attrs = [UMLAttribute(visibility="+", name="count", type="int")]
    ops   = [UMLOperation(visibility="-", name="reset", return_type="void")]
    node  = IRNode(
        id="cls1", label="Counter",
        shape=NodeShape.RECTANGLE,
        uml_attributes=attrs,
        uml_operations=ops,
    )
    ir = DiagramIR(category=DiagramCategory.UML_CLASS, nodes=[node])
    tikz = _gen(ir)
    assert "rectangle split" in tikz
    assert "count" in tikz
    assert "reset" in tikz


# ── Flowchart ─────────────────────────────────────────────────────────────────

def test_flowchart_terminator_style():
    n = IRNode(id="start", label="Start", shape=NodeShape.TERMINATOR, color=NodeColor.GREEN)
    ir = DiagramIR(category=DiagramCategory.FLOWCHART, nodes=[n])
    tikz = _gen(ir)
    assert "fc_terminator" in tikz


def test_flowchart_decision_style():
    n = IRNode(id="d1", label="Decision?", shape=NodeShape.DECISION, color=NodeColor.ORANGE)
    ir = DiagramIR(category=DiagramCategory.FLOWCHART, nodes=[n])
    tikz = _gen(ir)
    assert "gen_diamond" in tikz or "diamond" in tikz


# ── Quantum Circuit ───────────────────────────────────────────────────────────

def test_quantum_circuit_gate_style():
    h = IRNode(id="h0", label="H", shape=NodeShape.QUANTUM_GATE, qubit_index=0, gate_column=0)
    ir = DiagramIR(category=DiagramCategory.QUANTUM_CIRCUIT, nodes=[h])
    tikz = _gen(ir)
    assert "qgate" in tikz


def test_quantum_measurement_style():
    m = IRNode(id="m0", label="M", shape=NodeShape.MEASUREMENT, qubit_index=0, gate_column=1)
    ir = DiagramIR(category=DiagramCategory.QUANTUM_CIRCUIT, nodes=[m])
    tikz = _gen(ir)
    assert "qmeasure" in tikz


# ── ERD ───────────────────────────────────────────────────────────────────────

def test_erd_has_diamond_for_relation():
    entity = IRNode(id="e1", label="Customer", shape=NodeShape.RECTANGLE)
    rel    = IRNode(id="r1", label="places",   shape=NodeShape.DIAMOND)
    order  = IRNode(id="e2", label="Order",    shape=NodeShape.RECTANGLE)
    ir = DiagramIR(category=DiagramCategory.ERD, nodes=[entity, rel, order])
    tikz = _gen(ir)
    assert "gen_diamond" in tikz or "diamond" in tikz


# ── Architecture ──────────────────────────────────────────────────────────────

def test_architecture_cylinder_for_database():
    db = IRNode(id="db1", label="PostgreSQL", shape=NodeShape.CYLINDER, color=NodeColor.GREEN)
    ir = DiagramIR(category=DiagramCategory.ARCHITECTURE, nodes=[db])
    tikz = _gen(ir)
    assert "gen_cylinder" in tikz or "cylinder" in tikz


# ── Edge styles ───────────────────────────────────────────────────────────────

def test_dashed_edge_in_output():
    n1 = IRNode(id="n1", label="A")
    n2 = IRNode(id="n2", label="B")
    e  = IREdge(**{"from": "n1", "to": "n2", "style": "dashed"})
    ir = DiagramIR(nodes=[n1, n2], edges=[e])
    tikz = _gen(ir)
    assert "dashed" in tikz


def test_arrow_spec_inheritance():
    """Generalization (hollow arrow) for UML inheritance."""
    n1 = IRNode(id="n1", label="Animal")
    n2 = IRNode(id="n2", label="Dog")
    e  = IREdge(**{
        "from": "n2", "to": "n1",
        "arrow_head": "hollow",
        "arrow_tail": "none",
    })
    ir = DiagramIR(category=DiagramCategory.UML_CLASS, nodes=[n1, n2], edges=[e])
    tikz = _gen(ir)
    assert "Triangle" in tikz or "hollow" in tikz.lower()


# ── Resource allocation ────────────────────────────────────────────────────────

def test_resource_alloc_process_circle():
    p = IRNode(id="p1", label="P1", shape=NodeShape.CIRCLE, color=NodeColor.BLUE)
    r = IRNode(id="r1", label="R1", shape=NodeShape.RECTANGLE, color=NodeColor.GRAY)
    e = IREdge(**{"from": "p1", "to": "r1", "label": "request"})
    ir = DiagramIR(category=DiagramCategory.RESOURCE_ALLOC, nodes=[p, r], edges=[e])
    tikz = _gen(ir)
    assert "gen_circle" in tikz or "circle" in tikz
