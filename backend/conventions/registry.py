"""
Diagram Convention Registry.

Maps diagram categories to their convention profiles,
required TikZ styles, validation rules, and symbol definitions.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from backend.ir.schema import DiagramCategory, NodeShape, EdgeArrow


@dataclass
class ConventionProfile:
    """All category-specific rules for one diagram type."""
    category: DiagramCategory
    description: str

    # Shapes allowed in this category
    allowed_shapes: list[NodeShape] = field(default_factory=list)

    # Default shape for new nodes
    default_shape: NodeShape = NodeShape.ROUNDED

    # Required TikZ libraries (appended to \usetikzlibrary{...})
    tikz_libraries: list[str] = field(default_factory=list)

    # Category-specific TikZ style definitions (raw LaTeX snippets)
    tikz_styles: list[str] = field(default_factory=list)

    # Validation rules: list of (description, predicate) tuples
    # predicate(ir) → list[str] of error messages (empty = OK)
    validation_rules: list[tuple[str, Callable]] = field(default_factory=list)

    # Whether edges should use orthogonal routing by default
    prefer_orthogonal_edges: bool = False

    # Recommended layout direction
    recommended_direction: str = "LR"


# ── Individual convention profiles ───────────────────────────────────────────

def _uml_class_profile() -> ConventionProfile:
    return ConventionProfile(
        category=DiagramCategory.UML_CLASS,
        description="UML 2.x Class Diagram",
        allowed_shapes=[NodeShape.RECTANGLE, NodeShape.DOUBLE_RECT],
        default_shape=NodeShape.RECTANGLE,
        tikz_libraries=["positioning", "arrows.meta", "calc", "fit", "backgrounds",
                        "shapes.geometric", "shapes.multipart"],
        tikz_styles=[
            r"uml_class/.style={draw, thick, rectangle split, rectangle split parts=3, "
            r"text width=3.5cm, align=left, inner sep=4pt, font=\rmfamily\small}",
            r"uml_interface/.style={draw, thick, double, rectangle split, rectangle split parts=2, "
            r"text width=3.0cm, align=left, inner sep=4pt, font=\rmfamily\small}",
        ],
        prefer_orthogonal_edges=False,
        recommended_direction="TB",
    )


def _uml_use_case_profile() -> ConventionProfile:
    return ConventionProfile(
        category=DiagramCategory.UML_USE_CASE,
        description="UML 2.x Use Case Diagram",
        allowed_shapes=[NodeShape.ELLIPSE, NodeShape.ACTOR, NodeShape.RECTANGLE],
        default_shape=NodeShape.ELLIPSE,
        tikz_libraries=["positioning", "arrows.meta", "shapes.geometric", "fit", "backgrounds"],
        tikz_styles=[
            r"uml_actor/.style={draw=none, inner sep=2pt, align=center, font=\rmfamily\small}",
            r"uml_usecase/.style={draw, thick, ellipse, text width=2.4cm, align=center, "
            r"inner sep=3pt, font=\rmfamily\small}",
            r"system_boundary/.style={draw, dashed, thick, rounded corners=8pt, "
            r"fill=gray!4, inner sep=18pt}",
        ],
        prefer_orthogonal_edges=False,
        recommended_direction="LR",
    )


def _uml_sequence_profile() -> ConventionProfile:
    return ConventionProfile(
        category=DiagramCategory.UML_SEQUENCE,
        description="UML 2.x Sequence Diagram",
        allowed_shapes=[NodeShape.RECTANGLE, NodeShape.ACTOR],
        default_shape=NodeShape.RECTANGLE,
        tikz_libraries=["positioning", "arrows.meta", "calc"],
        tikz_styles=[
            r"lifeline/.style={draw, thick, rectangle, text width=2.5cm, minimum height=0.9cm, "
            r"align=center, inner sep=4pt, font=\rmfamily\small}",
            r"activation/.style={draw, thick, fill=blue!8, rectangle, minimum width=0.35cm}",
            r"msg_arrow/.style={->, thick, draw=black!80}",
            r"return_arrow/.style={->, dashed, draw=black!60}",
        ],
        prefer_orthogonal_edges=True,
        recommended_direction="LR",
    )


def _flowchart_profile() -> ConventionProfile:
    return ConventionProfile(
        category=DiagramCategory.FLOWCHART,
        description="Standard Flowchart",
        allowed_shapes=[
            NodeShape.TERMINATOR, NodeShape.PROCESS, NodeShape.DECISION,
            NodeShape.IO_BOX, NodeShape.RECTANGLE, NodeShape.DIAMOND,
        ],
        default_shape=NodeShape.PROCESS,
        tikz_libraries=["positioning", "arrows.meta", "shapes.geometric",
                        "shapes.symbols", "calc"],
        tikz_styles=[
            r"fc_terminator/.style={draw, thick, rounded corners=18pt, "
            r"text width=2.5cm, minimum height=1.0cm, align=center, inner sep=5pt, "
            r"fill=green!8, draw=green!70!black, font=\rmfamily\small}",
            r"fc_process/.style={draw, thick, rectangle, text width=2.8cm, "
            r"minimum height=1.0cm, align=center, inner sep=5pt, "
            r"fill=blue!6, draw=blue!70!black, font=\rmfamily\small}",
            r"fc_decision/.style={draw, thick, diamond, aspect=2.0, "
            r"text width=2.2cm, align=center, inner sep=3pt, "
            r"fill=orange!8, draw=orange!70!black, font=\rmfamily\small}",
            r"fc_io/.style={draw, thick, trapezium, trapezium left angle=80, "
            r"trapezium right angle=100, text width=2.5cm, align=center, inner sep=4pt, "
            r"fill=purple!6, draw=purple!70!black, font=\rmfamily\small}",
        ],
        prefer_orthogonal_edges=True,
        recommended_direction="TB",
    )


def _dfd_profile() -> ConventionProfile:
    return ConventionProfile(
        category=DiagramCategory.DFD,
        description="Data Flow Diagram (Yourdon-DeMarco)",
        allowed_shapes=[NodeShape.CIRCLE, NodeShape.RECTANGLE, NodeShape.DATA_STORE],
        default_shape=NodeShape.CIRCLE,
        tikz_libraries=["positioning", "arrows.meta", "shapes.geometric", "calc"],
        tikz_styles=[
            r"dfd_process/.style={draw, thick, circle, text width=1.8cm, "
            r"align=center, inner sep=3pt, fill=blue!6, font=\rmfamily\small}",
            r"dfd_entity/.style={draw, thick, rectangle, text width=2.4cm, "
            r"minimum height=1.0cm, align=center, inner sep=4pt, font=\rmfamily\small}",
            r"dfd_store/.style={draw, thick, "
            r"minimum width=2.8cm, minimum height=0.7cm, align=center, "
            r"inner sep=4pt, font=\rmfamily\small}",
        ],
        prefer_orthogonal_edges=False,
        recommended_direction="LR",
    )


def _erd_profile() -> ConventionProfile:
    return ConventionProfile(
        category=DiagramCategory.ERD,
        description="Entity Relationship Diagram",
        allowed_shapes=[NodeShape.RECTANGLE, NodeShape.DIAMOND, NodeShape.ELLIPSE],
        default_shape=NodeShape.RECTANGLE,
        tikz_libraries=["positioning", "arrows.meta", "shapes.geometric", "calc"],
        tikz_styles=[
            r"erd_entity/.style={draw, thick, rectangle, text width=2.8cm, "
            r"minimum height=0.9cm, align=center, inner sep=4pt, "
            r"fill=blue!5, font=\rmfamily\small}",
            r"erd_relation/.style={draw, thick, diamond, aspect=1.8, "
            r"text width=1.8cm, align=center, inner sep=3pt, "
            r"fill=orange!8, font=\rmfamily\small}",
            r"erd_attr/.style={draw, ellipse, text width=1.6cm, align=center, "
            r"inner sep=3pt, font=\rmfamily\footnotesize}",
            r"erd_weak/.style={draw, double, rectangle, text width=2.8cm, "
            r"minimum height=0.9cm, align=center, inner sep=4pt, font=\rmfamily\small}",
        ],
        prefer_orthogonal_edges=False,
        recommended_direction="TB",
    )


def _electrical_profile() -> ConventionProfile:
    return ConventionProfile(
        category=DiagramCategory.ELECTRICAL,
        description="Electrical / Electronic Circuit Diagram",
        allowed_shapes=[NodeShape.RECTANGLE, NodeShape.CIRCLE],
        default_shape=NodeShape.RECTANGLE,
        tikz_libraries=["positioning", "arrows.meta", "calc", "circuits.ee.IEC"],
        tikz_styles=[
            r"circuit_component/.style={circuit ee IEC, draw, thick}",
            r"wire/.style={draw, thick}",
            r"junction/.style={fill, circle, inner sep=1.5pt}",
        ],
        prefer_orthogonal_edges=True,
        recommended_direction="LR",
    )


def _digital_logic_profile() -> ConventionProfile:
    return ConventionProfile(
        category=DiagramCategory.DIGITAL_LOGIC,
        description="Digital Logic Circuit Diagram",
        allowed_shapes=[NodeShape.RECTANGLE],
        default_shape=NodeShape.RECTANGLE,
        tikz_libraries=["positioning", "arrows.meta", "calc",
                        "circuits.logic.IEC", "circuits.logic.US"],
        tikz_styles=[
            r"logic_gate/.style={circuit logic IEC, draw, thick}",
            r"logic_wire/.style={draw, thick}",
            r"logic_junction/.style={fill, circle, inner sep=1.5pt}",
        ],
        prefer_orthogonal_edges=True,
        recommended_direction="LR",
    )


def _quantum_profile() -> ConventionProfile:
    return ConventionProfile(
        category=DiagramCategory.QUANTUM_CIRCUIT,
        description="Quantum Circuit Diagram",
        allowed_shapes=[NodeShape.QUANTUM_GATE, NodeShape.MEASUREMENT, NodeShape.RECTANGLE],
        default_shape=NodeShape.QUANTUM_GATE,
        tikz_libraries=["positioning", "arrows.meta", "calc", "fit", "backgrounds"],
        tikz_styles=[
            r"qwire/.style={draw, thick}",
            r"qgate/.style={draw, thick, rectangle, minimum size=0.8cm, align=center, "
            r"fill=blue!8, font=\rmfamily\small}",
            r"qmeasure/.style={draw, thick, rectangle, minimum size=0.8cm, "
            r"fill=orange!10, font=\rmfamily\small}",
            r"qcontrol/.style={fill, circle, inner sep=2pt}",
            r"qtarget/.style={draw, circle, inner sep=4pt, thick}",
            r"qcwire/.style={draw, double, thin}",
        ],
        prefer_orthogonal_edges=False,
        recommended_direction="LR",
    )


def _resource_alloc_profile() -> ConventionProfile:
    return ConventionProfile(
        category=DiagramCategory.RESOURCE_ALLOC,
        description="Resource Allocation Graph",
        allowed_shapes=[NodeShape.CIRCLE, NodeShape.RECTANGLE],
        default_shape=NodeShape.CIRCLE,
        tikz_libraries=["positioning", "arrows.meta", "shapes.geometric", "calc"],
        tikz_styles=[
            r"ra_process/.style={draw, thick, circle, text width=1.4cm, "
            r"align=center, inner sep=3pt, fill=blue!6, font=\rmfamily\small}",
            r"ra_resource/.style={draw, thick, rectangle, text width=2.2cm, "
            r"minimum height=1.0cm, align=center, inner sep=4pt, font=\rmfamily\small}",
            r"ra_instance/.style={fill, circle, inner sep=2.5pt}",
            r"ra_request/.style={->, dashed, thick, draw=red!70!black}",
            r"ra_assign/.style={->, thick, draw=blue!70!black}",
        ],
        prefer_orthogonal_edges=False,
        recommended_direction="LR",
    )


def _architecture_profile() -> ConventionProfile:
    return ConventionProfile(
        category=DiagramCategory.ARCHITECTURE,
        description="Software / System Architecture Diagram",
        allowed_shapes=[NodeShape.RECTANGLE, NodeShape.ROUNDED, NodeShape.CYLINDER,
                        NodeShape.CLOUD, NodeShape.HEXAGON],
        default_shape=NodeShape.ROUNDED,
        tikz_libraries=["positioning", "arrows.meta", "calc", "fit", "backgrounds",
                        "shapes.geometric"],
        tikz_styles=[
            r"arch_service/.style={draw, thick, rectangle, rounded corners=4pt, "
            r"text width=3.0cm, minimum height=1.1cm, align=center, inner sep=5pt, "
            r"fill=blue!6, font=\rmfamily\small}",
            r"arch_db/.style={draw, thick, cylinder, shape border rotate=90, aspect=0.25, "
            r"text width=2.2cm, minimum height=1.2cm, align=center, inner sep=4pt, "
            r"fill=green!6, font=\rmfamily\small}",
            r"arch_boundary/.style={draw, dashed, thick, rounded corners=10pt, "
            r"fill=gray!3, inner sep=18pt}",
            r"arch_external/.style={draw, thick, cloud, cloud puffs=9, "
            r"text width=2.2cm, align=center, fill=orange!5, font=\rmfamily\small}",
        ],
        prefer_orthogonal_edges=False,
        recommended_direction="LR",
    )


def _neural_network_profile() -> ConventionProfile:
    return ConventionProfile(
        category=DiagramCategory.NEURAL_NETWORK,
        description="Neural Network Architecture Diagram",
        allowed_shapes=[NodeShape.CIRCLE, NodeShape.RECTANGLE, NodeShape.ROUNDED],
        default_shape=NodeShape.CIRCLE,
        tikz_libraries=["positioning", "arrows.meta", "calc", "fit", "backgrounds"],
        tikz_styles=[
            r"nn_neuron/.style={draw, thick, circle, minimum size=0.7cm, "
            r"fill=blue!8, font=\rmfamily\tiny}",
            r"nn_layer/.style={draw, dashed, rounded corners=6pt, "
            r"fill=gray!3, inner sep=12pt}",
            r"nn_edge/.style={->, thin, draw=black!50}",
        ],
        prefer_orthogonal_edges=False,
        recommended_direction="LR",
    )


def _generic_profile() -> ConventionProfile:
    return ConventionProfile(
        category=DiagramCategory.GENERIC,
        description="Generic / Custom Diagram",
        allowed_shapes=list(NodeShape),
        default_shape=NodeShape.ROUNDED,
        tikz_libraries=["positioning", "arrows.meta", "calc", "fit", "backgrounds",
                        "shapes.geometric"],
        tikz_styles=[],
        prefer_orthogonal_edges=False,
        recommended_direction="LR",
    )


# ── Registry ──────────────────────────────────────────────────────────────────

class ConventionRegistry:
    """
    Central registry mapping DiagramCategory → ConventionProfile.
    Adding a new category requires only registering a new profile here.
    """

    def __init__(self) -> None:
        self._profiles: dict[DiagramCategory, ConventionProfile] = {}
        self._register_defaults()

    def _register_defaults(self) -> None:
        for profile in [
            _uml_class_profile(),
            _uml_use_case_profile(),
            _uml_sequence_profile(),
            _flowchart_profile(),
            _dfd_profile(),
            _erd_profile(),
            _electrical_profile(),
            _digital_logic_profile(),
            _quantum_profile(),
            _resource_alloc_profile(),
            _architecture_profile(),
            _neural_network_profile(),
            _generic_profile(),
        ]:
            self._profiles[profile.category] = profile

        # Alias similar categories to their closest profile
        aliases = {
            DiagramCategory.UML_OBJECT:     DiagramCategory.UML_CLASS,
            DiagramCategory.UML_ACTIVITY:   DiagramCategory.FLOWCHART,
            DiagramCategory.UML_STATE:      DiagramCategory.FSM,
            DiagramCategory.UML_COMPONENT:  DiagramCategory.ARCHITECTURE,
            DiagramCategory.UML_DEPLOYMENT: DiagramCategory.ARCHITECTURE,
            DiagramCategory.UML_PACKAGE:    DiagramCategory.ARCHITECTURE,
            DiagramCategory.BPMN:           DiagramCategory.FLOWCHART,
            DiagramCategory.WORKFLOW:       DiagramCategory.FLOWCHART,
            DiagramCategory.DB_SCHEMA:      DiagramCategory.ERD,
            DiagramCategory.NETWORK:        DiagramCategory.ARCHITECTURE,
            DiagramCategory.CLOUD:          DiagramCategory.ARCHITECTURE,
            DiagramCategory.MICROSERVICES:  DiagramCategory.ARCHITECTURE,
            DiagramCategory.BLOCK_DIAGRAM:  DiagramCategory.GENERIC,
            DiagramCategory.ML_PIPELINE:    DiagramCategory.GENERIC,
            DiagramCategory.FSM:            DiagramCategory.GENERIC,
            DiagramCategory.DECISION_TREE:  DiagramCategory.FLOWCHART,
            DiagramCategory.GRAPH:          DiagramCategory.GENERIC,
            DiagramCategory.SIGNAL_FLOW:    DiagramCategory.GENERIC,
        }
        for alias_cat, base_cat in aliases.items():
            if alias_cat not in self._profiles and base_cat in self._profiles:
                self._profiles[alias_cat] = self._profiles[base_cat]

    def get(self, category: DiagramCategory) -> ConventionProfile:
        return self._profiles.get(category, self._profiles[DiagramCategory.GENERIC])

    def register(self, profile: ConventionProfile) -> None:
        """Register a custom category profile."""
        self._profiles[profile.category] = profile

    @property
    def all_categories(self) -> list[DiagramCategory]:
        return list(self._profiles.keys())


# Singleton
_registry = ConventionRegistry()


def get_registry() -> ConventionRegistry:
    return _registry
