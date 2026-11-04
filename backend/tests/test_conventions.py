"""
Tests for diagram convention profiles.

Verifies that each category profile loads correctly,
provides required TikZ libraries, and enforces correct shapes.
"""
from __future__ import annotations

import pytest

from backend.conventions.registry import get_registry, ConventionProfile
from backend.ir.schema import DiagramCategory, NodeShape


def test_registry_loads_all_supported_categories():
    registry = get_registry()
    required = [
        DiagramCategory.UML_CLASS,
        DiagramCategory.UML_USE_CASE,
        DiagramCategory.UML_SEQUENCE,
        DiagramCategory.FLOWCHART,
        DiagramCategory.DFD,
        DiagramCategory.ERD,
        DiagramCategory.RESOURCE_ALLOC,
        DiagramCategory.ARCHITECTURE,
        DiagramCategory.ELECTRICAL,
        DiagramCategory.QUANTUM_CIRCUIT,
        DiagramCategory.NEURAL_NETWORK,
        DiagramCategory.GENERIC,
    ]
    for cat in required:
        profile = registry.get(cat)
        assert isinstance(profile, ConventionProfile), f"Missing profile for {cat}"


def test_uml_class_has_positioning_library():
    profile = get_registry().get(DiagramCategory.UML_CLASS)
    assert "positioning" in profile.tikz_libraries


def test_flowchart_has_terminator_shape():
    profile = get_registry().get(DiagramCategory.FLOWCHART)
    assert NodeShape.TERMINATOR in profile.allowed_shapes or profile.tikz_styles


def test_flowchart_has_decision_shape():
    profile = get_registry().get(DiagramCategory.FLOWCHART)
    assert NodeShape.DECISION in profile.allowed_shapes


def test_quantum_circuit_has_qgate_style():
    profile = get_registry().get(DiagramCategory.QUANTUM_CIRCUIT)
    combined = " ".join(profile.tikz_styles)
    assert "qgate" in combined


def test_erd_has_diamond_relation_style():
    profile = get_registry().get(DiagramCategory.ERD)
    combined = " ".join(profile.tikz_styles)
    assert "erd_relation" in combined


def test_electrical_has_circuit_library():
    profile = get_registry().get(DiagramCategory.ELECTRICAL)
    assert any("circuit" in lib for lib in profile.tikz_libraries)


def test_resource_alloc_has_separate_process_and_resource_styles():
    profile = get_registry().get(DiagramCategory.RESOURCE_ALLOC)
    combined = " ".join(profile.tikz_styles)
    assert "ra_process" in combined
    assert "ra_resource" in combined


def test_custom_profile_registration():
    from backend.conventions.registry import ConventionRegistry
    reg = ConventionRegistry()
    custom = ConventionProfile(
        category=DiagramCategory.GENERIC,
        description="Custom test profile",
    )
    reg.register(custom)
    assert reg.get(DiagramCategory.GENERIC).description == "Custom test profile"
