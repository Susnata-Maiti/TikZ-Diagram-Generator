"""
Tests for the validation pipeline.

Tests all stages including semantic, graph, geometric, and typography validation.
"""
from __future__ import annotations

import pytest

from backend.ir.schema import (
    DiagramIR, DiagramCategory, Direction,
    IRNode, IRGroup, IREdge, NodeShape, NodeColor,
)
from backend.validation.pipeline import ValidationPipeline
from backend.layout.engine import run_layout


def _simple_ir() -> DiagramIR:
    n1 = IRNode(id="n1", label="A", shape=NodeShape.ROUNDED)
    n2 = IRNode(id="n2", label="B", shape=NodeShape.ROUNDED)
    e  = IREdge(**{"from": "n1", "to": "n2"})
    return DiagramIR(nodes=[n1, n2], edges=[e])


def test_semantic_validation_passes_valid_ir():
    pipeline = ValidationPipeline()
    ir = _simple_ir()
    result = pipeline.validate_semantic(ir)
    assert result.passed


def test_semantic_validation_fails_empty_ir():
    pipeline = ValidationPipeline()
    ir = DiagramIR()
    result = pipeline.validate_semantic(ir)
    assert not result.passed
    assert any("no nodes" in e.lower() for e in result.errors)


def test_semantic_validation_fails_missing_edge_node():
    pipeline = ValidationPipeline()
    n1 = IRNode(id="n1", label="A")
    e  = IREdge(**{"from": "n1", "to": "GHOST"})
    ir = DiagramIR(nodes=[n1], edges=[e])
    result = pipeline.validate_semantic(ir)
    assert not result.passed


def test_graph_validation_warns_isolated_node():
    pipeline = ValidationPipeline()
    n1 = IRNode(id="n1", label="Connected A")
    n2 = IRNode(id="n2", label="Connected B")
    n3 = IRNode(id="n3", label="Isolated C")  # no edges
    e  = IREdge(**{"from": "n1", "to": "n2"})
    ir = DiagramIR(nodes=[n1, n2, n3], edges=[e])
    result = pipeline.validate_graph(ir)
    assert any("n3" in w or "Isolated" in w for w in result.warnings)


def test_geometry_validation_detects_overlap():
    """
    Place two nodes at the same (x, y) and verify the geometry validator
    catches the overlap.
    """
    from backend.ir.schema import NodeGeometry
    pipeline = ValidationPipeline()
    n1 = IRNode(id="n1", label="A")
    n2 = IRNode(id="n2", label="B")
    # Force identical geometry to create guaranteed overlap
    n1.geometry = NodeGeometry(x=0.0, y=0.0, width=3.0, height=1.2)
    n2.geometry = NodeGeometry(x=0.0, y=0.0, width=3.0, height=1.2)
    ir = DiagramIR(nodes=[n1, n2])
    result = pipeline.validate_geometry(ir)
    assert any("n1" in w or "n2" in w for w in result.warnings)


def test_layout_resolves_overlaps():
    """After running the layout engine, same-layer nodes must not overlap."""
    nodes = [IRNode(id=f"n{i}", label=f"Node {i}") for i in range(5)]
    ir = DiagramIR(nodes=nodes)
    ir = run_layout(ir)
    pipeline = ValidationPipeline()
    result = pipeline.validate_geometry(ir)
    # No overlap warnings after layout
    assert len(result.warnings) == 0


def test_typography_validation_returns_result():
    pipeline = ValidationPipeline()
    result = pipeline.validate_typography()
    assert result.stage == "typography"
    assert isinstance(result.passed, bool)


def test_validation_pipeline_full_no_compilation():
    """Full pipeline without compilation stage (no pdflatex required)."""
    pipeline = ValidationPipeline()
    ir = _simple_ir()
    ir = run_layout(ir)
    from backend.tikz.generator import TikZGenerator
    tikz = TikZGenerator().generate(ir)
    # Don't attempt compilation – just check IR stages pass
    sem = pipeline.validate_semantic(ir)
    graph = pipeline.validate_graph(ir)
    geo = pipeline.validate_geometry(ir)
    assert sem.passed
    assert graph.passed
    assert geo.passed


def test_self_loop_warning():
    pipeline = ValidationPipeline()
    n1 = IRNode(id="n1", label="A")
    e  = IREdge(**{"from": "n1", "to": "n1"})  # self-loop
    ir = DiagramIR(nodes=[n1], edges=[e])
    result = pipeline.validate_graph(ir)
    assert any("self-loop" in w.lower() or "n1" in w for w in result.warnings)
