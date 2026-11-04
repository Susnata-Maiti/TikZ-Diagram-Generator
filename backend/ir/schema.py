"""
JSON Intermediate Representation schema and Pydantic models.

The IR is the single source of truth for every diagram.
TikZ, SVG, or any other renderer must read from this structure –
never from raw LaTeX text.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Optional
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator, model_validator


# ── Enums ─────────────────────────────────────────────────────────────────────

class DiagramCategory(str, Enum):
    UML_CLASS          = "uml_class"
    UML_OBJECT         = "uml_object"
    UML_USE_CASE       = "uml_use_case"
    UML_SEQUENCE       = "uml_sequence"
    UML_ACTIVITY       = "uml_activity"
    UML_STATE          = "uml_state"
    UML_COMPONENT      = "uml_component"
    UML_DEPLOYMENT     = "uml_deployment"
    UML_PACKAGE        = "uml_package"
    FLOWCHART          = "flowchart"
    DFD                = "dfd"
    BPMN               = "bpmn"
    WORKFLOW           = "workflow"
    RESOURCE_ALLOC     = "resource_allocation"
    ERD                = "erd"
    DB_SCHEMA          = "db_schema"
    ARCHITECTURE       = "architecture"
    NETWORK            = "network"
    CLOUD              = "cloud"
    MICROSERVICES      = "microservices"
    ELECTRICAL         = "electrical"
    DIGITAL_LOGIC      = "digital_logic"
    QUANTUM_CIRCUIT    = "quantum_circuit"
    BLOCK_DIAGRAM      = "block_diagram"
    NEURAL_NETWORK     = "neural_network"
    ML_PIPELINE        = "ml_pipeline"
    FSM                = "fsm"
    DECISION_TREE      = "decision_tree"
    GRAPH              = "graph"
    SIGNAL_FLOW        = "signal_flow"
    GENERIC            = "generic"


class Direction(str, Enum):
    LR = "LR"   # left-to-right
    TB = "TB"   # top-to-bottom
    RL = "RL"
    BT = "BT"


class NodeShape(str, Enum):
    RECTANGLE   = "rectangle"
    ROUNDED     = "rounded"
    DIAMOND     = "diamond"
    CYLINDER    = "cylinder"
    CIRCLE      = "circle"
    ELLIPSE     = "ellipse"
    PARALLELOGRAM = "parallelogram"
    DOUBLE_RECT = "double_rect"   # UML interface stereotype
    ACTOR       = "actor"         # UML use case actor (stick figure)
    CLOUD       = "cloud"
    NOTE        = "note"
    HEXAGON     = "hexagon"
    TERMINATOR  = "terminator"    # flowchart start/end
    PROCESS     = "process"       # flowchart process
    DECISION    = "decision"      # flowchart decision = diamond
    IO_BOX      = "io_box"        # parallelogram input/output
    DATA_STORE  = "data_store"    # DFD open rectangle
    QUANTUM_GATE = "quantum_gate"
    MEASUREMENT  = "measurement"


class NodeColor(str, Enum):
    BLUE   = "blue"
    GREEN  = "green"
    ORANGE = "orange"
    PURPLE = "purple"
    GRAY   = "gray"
    RED    = "red"
    TEAL   = "teal"
    YELLOW = "yellow"
    WHITE  = "white"
    BLACK  = "black"


class EdgeRouting(str, Enum):
    DIRECT          = "direct"
    ORTHOGONAL_UP   = "orthogonal_up"
    ORTHOGONAL_DOWN = "orthogonal_down"
    ORTHOGONAL      = "orthogonal"
    CURVED          = "curved"
    SELF_LOOP       = "self_loop"


class EdgeStyle(str, Enum):
    SOLID   = "solid"
    DASHED  = "dashed"
    DOTTED  = "dotted"
    DOUBLE  = "double"


class EdgeArrow(str, Enum):
    NONE          = "none"
    OPEN          = "open"       # →
    FILLED        = "filled"     # ▶
    HOLLOW        = "hollow"     # △ (generalization)
    DIAMOND_OPEN  = "diamond_open"     # ◇ aggregation
    DIAMOND_FILLED = "diamond_filled"  # ◆ composition
    CROW_ONE      = "crow_one"
    CROW_MANY     = "crow_many"
    CROW_ZERO_ONE = "crow_zero_one"
    CROW_ONE_MANY = "crow_one_many"
    CROW_ZERO_MANY = "crow_zero_many"


class NotationProfile(str, Enum):
    UML_2X       = "uml_2x"
    BPMN_2_0     = "bpmn_2_0"
    CHEN_ERD     = "chen_erd"
    CROWS_FOOT   = "crows_foot"
    YOURDON_DFD  = "yourdon_dfd"
    GANE_SARSON  = "gane_sarson"
    IEEE_CIRCUIT = "ieee_circuit"
    QUANTUM_STD  = "quantum_std"
    DEFAULT      = "default"


# ── Node models ───────────────────────────────────────────────────────────────

class UMLAttribute(BaseModel):
    visibility: str = "+"    # +/-/#/~
    name: str
    type: str = ""
    default: str = ""

    def to_latex(self) -> str:
        base = f"{self.visibility} {self.name}"
        if self.type:
            base += f" : {self.type}"
        if self.default:
            base += f" = {self.default}"
        return base


class UMLOperation(BaseModel):
    visibility: str = "+"
    name: str
    params: str = ""
    return_type: str = ""

    def to_latex(self) -> str:
        base = f"{self.visibility} {self.name}({self.params})"
        if self.return_type:
            base += f" : {self.return_type}"
        return base


class NodeGeometry(BaseModel):
    """Computed by the layout engine – never set manually in prompts."""
    x: float = 0.0       # cm from origin
    y: float = 0.0
    width: float = 3.0   # cm
    height: float = 1.2  # cm


class IRNode(BaseModel):
    id: str = Field(default_factory=lambda: f"n{uuid4().hex[:6]}")
    label: str
    shape: NodeShape = NodeShape.ROUNDED
    color: NodeColor = NodeColor.BLUE
    group: Optional[str] = None   # group id
    layer: int = 0                # layout layer (computed)

    # Category-specific extras
    stereotype: Optional[str] = None  # UML stereotype «interface» etc.
    uml_attributes: list[UMLAttribute] = Field(default_factory=list)
    uml_operations: list[UMLOperation] = Field(default_factory=list)

    # Quantum circuit
    qubit_index: Optional[int] = None
    gate_column: Optional[int] = None

    # Arbitrary extra key-value properties
    properties: dict[str, Any] = Field(default_factory=dict)

    # Computed by layout engine
    geometry: NodeGeometry = Field(default_factory=NodeGeometry)

    @field_validator("label")
    @classmethod
    def truncate_label(cls, v: str) -> str:
        return v[:80]  # prevent runaway labels


class IRGroup(BaseModel):
    id: str = Field(default_factory=lambda: f"g{uuid4().hex[:6]}")
    label: str
    color: NodeColor = NodeColor.GRAY
    style: str = "dashed"   # "dashed" | "solid"

    geometry: NodeGeometry = Field(default_factory=NodeGeometry)


class IREdge(BaseModel):
    id: str = Field(default_factory=lambda: f"e{uuid4().hex[:6]}")
    from_node: str = Field(alias="from")
    to_node: str = Field(alias="to")
    label: str = ""
    routing: EdgeRouting = EdgeRouting.DIRECT
    style: EdgeStyle = EdgeStyle.SOLID
    arrow_tail: EdgeArrow = EdgeArrow.NONE
    arrow_head: EdgeArrow = EdgeArrow.OPEN
    multiplicity_tail: str = ""
    multiplicity_head: str = ""
    bend_angle: int = 0   # for curved edges, degrees

    model_config = {"populate_by_name": True}

    @field_validator("label")
    @classmethod
    def truncate_label(cls, v: str) -> str:
        return v[:40]


# ── Top-level IR ──────────────────────────────────────────────────────────────

class ValidationResult(BaseModel):
    passed: bool = True
    stage: str = ""
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ResearchSource(BaseModel):
    url: str
    title: str = ""
    snippet: str = ""
    relevance_note: str = ""


class DiagramIR(BaseModel):
    """
    Central Intermediate Representation for a diagram.

    All agents read and write this structure.
    The TikZ generator converts it to LaTeX.
    """
    id: str = Field(default_factory=lambda: uuid4().hex)
    category: DiagramCategory = DiagramCategory.GENERIC
    notation_profile: NotationProfile = NotationProfile.DEFAULT
    direction: Direction = Direction.LR
    title: str = ""

    groups: list[IRGroup] = Field(default_factory=list)
    nodes: list[IRNode] = Field(default_factory=list)
    edges: list[IREdge] = Field(default_factory=list)

    # Metadata
    agent_summary: str = ""
    research_sources: list[ResearchSource] = Field(default_factory=list)
    validation: ValidationResult = Field(default_factory=ValidationResult)
    properties: dict[str, Any] = Field(default_factory=dict)

    # Raw user prompt that produced this IR (for repair context)
    source_prompt: str = ""

    @model_validator(mode="after")
    def _validate_edge_refs(self) -> "DiagramIR":
        node_ids = {n.id for n in self.nodes}
        for edge in self.edges:
            if edge.from_node not in node_ids:
                self.validation.warnings.append(
                    f"Edge {edge.id}: from_node '{edge.from_node}' not found"
                )
            if edge.to_node not in node_ids:
                self.validation.warnings.append(
                    f"Edge {edge.id}: to_node '{edge.to_node}' not found"
                )
        return self

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(by_alias=True)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DiagramIR":
        return cls.model_validate(data)
