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


def test_geometry_validation_detects_group_overlap():
    from backend.ir.schema import NodeGeometry
    pipeline = ValidationPipeline()
    g1 = IRGroup(id="g1", label="Tier 1", geometry=NodeGeometry(x=0.0, y=0.0, width=4.0, height=4.0))
    g2 = IRGroup(id="g2", label="Tier 2", geometry=NodeGeometry(x=2.0, y=2.0, width=4.0, height=4.0))
    ir = DiagramIR(groups=[g1, g2])
    result = pipeline.validate_geometry(ir)
    assert any("g1" in w and "g2" in w for w in result.warnings)


def test_geometry_validation_detects_foreign_node_in_group():
    from backend.ir.schema import NodeGeometry
    pipeline = ValidationPipeline()
    g1 = IRGroup(id="g1", label="Tier 1", geometry=NodeGeometry(x=0.0, y=0.0, width=5.0, height=5.0))
    # Foreign node sitting inside group g1's bounding box
    n1 = IRNode(id="foreign1", label="Alien", group=None, geometry=NodeGeometry(x=2.5, y=2.5, width=1.0, height=1.0))
    ir = DiagramIR(groups=[g1], nodes=[n1])
    result = pipeline.validate_geometry(ir)
    assert any("foreign1" in w and "g1" in w for w in result.warnings)


def test_complex_architecture_layout_passes_all_geometry_validation():
    """A realistic multi-tier system with groups and connections must pass all geometry checks without warning."""
    g1 = IRGroup(id="g_client", label="Client Layer")
    g2 = IRGroup(id="g_api", label="Gateway Layer")
    g3 = IRGroup(id="g_data", label="Data Storage")

    n1 = IRNode(id="n_web", label="Web App", group="g_client")
    n2 = IRNode(id="n_mobile", label="Mobile App", group="g_client")
    n3 = IRNode(id="n_gw", label="Kong API Gateway", group="g_api")
    n4 = IRNode(id="n_auth", label="Auth Service", group="g_api")
    n5 = IRNode(id="n_pg", label="PostgreSQL Primary", shape=NodeShape.CYLINDER, group="g_data")
    n6 = IRNode(id="n_redis", label="Redis Cache Cluster", shape=NodeShape.CYLINDER, group="g_data")

    edges = [
        IREdge(**{"from": "n_web", "to": "n_gw"}),
        IREdge(**{"from": "n_mobile", "to": "n_gw"}),
        IREdge(**{"from": "n_gw", "to": "n_auth"}),
        IREdge(**{"from": "n_auth", "to": "n_redis"}),
        IREdge(**{"from": "n_auth", "to": "n_pg"}),
    ]

    ir = DiagramIR(
        category=DiagramCategory.ARCHITECTURE,
        direction=Direction.LR,
        groups=[g1, g2, g3],
        nodes=[n1, n2, n3, n4, n5, n6],
        edges=edges,
    )
    ir = run_layout(ir)
    pipeline = ValidationPipeline()
    report = pipeline.validate_geometry(ir)
    assert len(report.warnings) == 0, f"Expected 0 geometry warnings, got: {report.warnings}"


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
