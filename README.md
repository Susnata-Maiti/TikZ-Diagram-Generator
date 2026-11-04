# TikZ Diagram Generator — Powered by IBM Granite

An AI-powered, research-assisted, multi-agent diagram generation platform.
Transforms natural-language descriptions, technical requirements, and hand-drawn sketches
into accurate, publication-quality LaTeX/TikZ diagrams with deterministic layout.

---

## Table of Contents

1. [Project Architecture](#1-project-architecture)
2. [Supported Diagram Types](#2-supported-diagram-types)
3. [Diagram Convention Engine](#3-diagram-convention-engine)
4. [IBM Granite Integration](#4-ibm-granite-integration)
5. [Research Capabilities](#5-research-capabilities)
6. [IR Structure](#6-ir-structure)
7. [Computational Geometry Approach](#7-computational-geometry-approach)
8. [TikZ Generation](#8-tikz-generation)
9. [Typography Configuration](#9-typography-configuration)
10. [Validation Pipeline](#10-validation-pipeline)
11. [Local Setup](#11-local-setup)
12. [Vercel Deployment](#12-vercel-deployment)
13. [Worker Deployment](#13-worker-deployment)
14. [Testing](#14-testing)
15. [Known Limitations](#15-known-limitations)

---

## 1. Project Architecture

```
tikz-diagram-generator/
├── backend/
│   ├── main.py                 ← FastAPI application entry point
│   ├── config.py               ← Pydantic Settings (reads .env)
│   ├── agents/
│   │   ├── granite_client.py   ← IBM watsonx.ai wrapper + retry logic
│   │   ├── intent_agent.py     ← NL → IR + route commands
│   │   └── technical_reasoning_agent.py ← Logical correctness review
│   ├── api/
│   │   └── routes.py           ← All REST endpoints
│   ├── compiler/
│   │   └── latex_compiler.py   ← pdflatex / texlive.net compilation
│   ├── conventions/
│   │   └── registry.py         ← Convention profiles for all categories
│   ├── ir/
│   │   └── schema.py           ← Pydantic IR models (central data structure)
│   ├── layout/
│   │   └── engine.py           ← Layered layout + collision detection
│   ├── research/
│   │   └── research_manager.py ← Web search + Granite-assisted analysis
│   ├── services/
│   │   ├── diagram_service.py  ← End-to-end orchestration
│   │   └── history_service.py  ← Undo/redo stack
│   ├── sketch/
│   │   └── image_parser.py     ← Vision model sketch interpretation
│   ├── tikz/
│   │   ├── generator.py        ← IR → TikZ LaTeX generation
│   │   └── repair_prompts.py   ← Prompts for self-repair loop
│   ├── validation/
│   │   └── pipeline.py         ← 6-stage validation + auto-repair
│   └── tests/                  ← Pytest test suite
│
├── frontend/
│   ├── pages/
│   │   ├── index.js            ← Main UI
│   │   └── _app.js
│   ├── hooks/
│   │   └── useDiagramState.js  ← React state hook
│   ├── lib/
│   │   └── api.js              ← Backend API client
│   └── styles/
│       └── globals.css
│
├── worker/
│   ├── main.py                 ← Worker entry point
│   └── Dockerfile              ← Container for computationally intensive ops
│
├── .env.example                ← Environment variable template
├── vercel.json                 ← Vercel frontend configuration
└── README.md
```

### Multi-Agent Flow

```
User prompt
    │
    ▼
[Intent Agent]  ──(IBM Granite)──►  Structured JSON IR
    │
    ├─ [Research Agent]  ──(web + Granite)──►  Enhanced technical prompt
    │
    ├─ [Technical Reasoning Agent]  ──(Granite)──►  Logical review
    │
    ▼
[Convention Registry]  ──►  Category-specific profile + TikZ styles
    │
    ▼
[Layout Engine]  ──(deterministic)──►  Node positions + group sizes
    │
    ▼
[TikZ Generator]  ──►  Complete LaTeX document
    │
    ▼
[Validation Pipeline]  ──►  Semantic + Graph + Geometry + Typography checks
    │         │
    │   [Repair Agent]  ──(Granite)──►  Fixed TikZ code
    │
    ▼
[LaTeX Compiler]  ──(pdflatex)──►  PDF + PNG preview
    │
    ▼
REST API response  →  Frontend display
```

---

## 2. Supported Diagram Types

| Category                    | Key Conventions Applied                                              |
|-----------------------------|----------------------------------------------------------------------|
| UML Class Diagram           | Compartments, visibility (+/-/#/~), UML arrows                       |
| UML Use Case Diagram        | Actor stick figures, system boundary, use case ellipses              |
| UML Sequence Diagram        | Lifelines, activation bars, message arrows, return arrows            |
| UML Activity Diagram        | Decision nodes, fork/join, swimlanes                                 |
| UML State Diagram           | States, transitions with event/guard/action                          |
| Flowchart                   | Terminators, process rectangles, decision diamonds, I/O parallelograms |
| Data Flow Diagram (DFD)     | Yourdon-DeMarco / Gane-Sarson notation, data flows, data stores      |
| BPMN                        | Events, tasks, gateways, sequence flows                              |
| ERD                         | Chen (entity/attribute/relationship) or Crow's Foot notation         |
| Resource Allocation Graph   | Process circles, resource rectangles, request/assignment edges       |
| Architecture Diagram        | Services, databases, boundaries, external systems                    |
| Electrical Circuit          | IEEE symbols: resistors, capacitors, transistors, op-amps            |
| Digital Logic Circuit       | AND/OR/NOT/NAND/NOR/XOR/XNOR gates, flip-flops                      |
| Quantum Circuit             | Qubit wires, gate boxes, CNOT, Hadamard, measurement symbols         |
| Neural Network              | Neuron circles, layer groups                                         |
| ML Pipeline                 | Processing stages with containers                                    |
| FSM / Decision Tree / Graph | States, transitions, tree structure                                  |

---

## 3. Diagram Convention Engine

Each diagram category has a `ConventionProfile` registered in `backend/conventions/registry.py`.
It specifies:

- **allowed_shapes** – the valid TikZ shapes for this category.
- **tikz_libraries** – the `\usetikzlibrary{...}` entries required.
- **tikz_styles** – reusable named styles (`uml_class`, `fc_terminator`, `qgate`, etc.).
- **prefer_orthogonal_edges** – routing preference.
- **recommended_direction** – LR or TB.

To add a new diagram category:

1. Add an entry to `DiagramCategory` enum in `backend/ir/schema.py`.
2. Write a `_yourtype_profile()` function in `backend/conventions/registry.py`.
3. Register it in `ConventionRegistry._register_defaults()`.

No other code needs to change.

---

## 4. IBM Granite Integration

`backend/agents/granite_client.py` wraps `ibm_watsonx_ai.foundation_models.ModelInference`.

Key characteristics:
- **Code model**: `ibm/granite-4-h-small` for IR generation, routing, and repair.
- **Vision model**: `meta-llama/llama-4-maverick-17b-128e-instruct-fp8` for sketch interpretation.
- **Retry logic**: Exponential back-off, 3 attempts, final fallback to `generate_text`.
- **No hardcoded credentials**: All keys read from environment variables.
- **Chat-first**: Uses `model.chat(messages=...)` for structured prompts.

Agents that use Granite:
- `IntentAgent` – NL → IR, refinement, command routing.
- `TechnicalReasoningAgent` – Logical review.
- `ResearchAgent` – Technical analysis from web snippets.
- `SketchInterpreter` – Vision-based shape extraction.
- `ValidationPipeline.repair_tikz()` – Self-repair loop.

---

## 5. Research Capabilities

`backend/research/research_manager.py`:

1. **WebSearcher** queries DuckDuckGo (default), SerpAPI, or Brave Search.
2. Results are passed to Granite for technical analysis.
3. Granite produces:
   - `technical_summary` – concise description.
   - `component_list` – key parts of the technical system.
   - `connection_notes` – how parts relate.
   - `recommended_diagram_prompt` – enriched prompt for generation.
4. `DiagramService.generate()` merges the research into the prompt before calling the intent agent.
5. Source URLs are stored in the IR's `research_sources` field.

**Provider configuration** (in `.env`):
```
SEARCH_PROVIDER=duckduckgo    # default, no key required
SEARCH_PROVIDER=serpapi       # requires SEARCH_API_KEY
SEARCH_PROVIDER=brave         # requires SEARCH_API_KEY
```

---

## 6. IR Structure

The `DiagramIR` Pydantic model (`backend/ir/schema.py`) is the single source of truth.

```json
{
  "id":               "abc123",
  "category":         "flowchart",
  "notation_profile": "default",
  "direction":        "TB",
  "title":            "Login Process",
  "groups": [
    { "id": "g1", "label": "Auth System", "color": "gray", "style": "dashed" }
  ],
  "nodes": [
    {
      "id":             "n1",
      "label":          "Start",
      "shape":          "terminator",
      "color":          "green",
      "group":          null,
      "stereotype":     null,
      "uml_attributes": [],
      "uml_operations": [],
      "qubit_index":    null,
      "gate_column":    null,
      "properties":     {},
      "geometry":       { "x": 0.0, "y": 0.0, "width": 2.5, "height": 0.9 }
    }
  ],
  "edges": [
    {
      "id":               "e1",
      "from":             "n1",
      "to":               "n2",
      "label":            "begin",
      "routing":          "direct",
      "style":            "solid",
      "arrow_head":       "open",
      "arrow_tail":       "none",
      "multiplicity_tail":"",
      "multiplicity_head":""
    }
  ],
  "agent_summary":      "Login flowchart generated.",
  "research_sources":   [],
  "validation":         { "passed": true, "stage": "", "errors": [], "warnings": [] }
}
```

Every user refinement updates the IR – the TikZ code is always regenerated from it.
This guarantees structural consistency and prevents drift between the IR and the LaTeX.

---

## 7. Computational Geometry Approach

`backend/layout/engine.py` implements a **layered layout** algorithm:

1. **Layer assignment** (`_assign_layers`)  
   Topological sort of the directed graph. Each node gets a layer index based on its
   longest predecessor chain. Cycles are handled conservatively (placed at layer 0).

2. **Node dimension calculation** (`_node_dimensions`)  
   Estimates width and height from:
   - Label character count and word-wrap at 22 chars per line.
   - UML class members (attributes + operations).
   - Stereotype header.
   Uses proportional character-width constants derived from Times New Roman metrics.

3. **Position assignment** (`_assign_positions`)  
   Nodes in each layer are spaced along the cross-axis using configurable gap constants.
   Main-axis cursor advances by the widest/tallest node in each layer plus the gap.

4. **Group container sizing** (`_size_groups`)  
   The bounding box of all member nodes is computed and padded by `layout_container_inner_sep_cm`.

5. **Collision resolution** (`_resolve_collisions`)  
   Same-layer nodes are checked for bounding-box overlap and pushed apart iteratively
   (max 10 iterations). A minimum separation of 0.3 cm is enforced.

Granite is **never** asked to produce coordinates. The model determines logical structure;
the geometry engine determines physical positions.

---

## 8. TikZ Generation

`backend/tikz/generator.py`:

- Loads the `ConventionProfile` for the IR's category.
- Writes a `\documentclass[tikz,border=14pt]{standalone}` document.
- Emits preamble with `fontspec` or `mathptmx` depending on `USE_FONTSPEC`.
- Generates `\usetikzlibrary{...}` from the union of required libraries.
- Defines base shape styles plus category-specific styles.
- Emits one `\node[...]` per IR node using `at (x.xxxcm, y.yyycm)` coordinates from the layout engine.
- UML class nodes use `rectangle split` with up to 3 parts (name / attributes / operations).
- Group containers are drawn in the `pgfonlayer{background}` using `fit=(n1)(n2)`.
- Edges use explicit anchor connections (`.east`, `.west`, `.north`, `.south`).
- Edge labels use `fill=white, inner sep=2.5pt` to prevent line-text collision.
- Arrow tip mapping covers UML, ERD Crow's Foot, and generic directional arrows.

---

## 9. Typography Configuration

All diagram text uses **Times New Roman** when available.

Two compilation paths:

| `USE_FONTSPEC` | Compiler | Font mechanism |
|---|---|---|
| `true`  | `lualatex` or `xelatex` | `\usepackage{fontspec}` + `\setmainfont{Times New Roman}` |
| `false` | `pdflatex`              | `\usepackage{mathptmx}` (visually close substitute) |

**Font availability check**: `ValidationPipeline.validate_typography()` runs `fc-list` to verify
the font is installed. A warning is emitted if it is not found; generation continues with the fallback.

**Note**: `TeX Gyre Termes` is a metrically compatible open-source alternative to Times New Roman
but is NOT described as the same font. When the fallback is used, the validation warning clearly
states which font is in use.

**Local development with pdflatex (recommended)**:
Set `USE_FONTSPEC=false` in your `.env` file. `mathptmx` is always available in any TeX Live installation.

---

## 10. Validation Pipeline

`backend/validation/pipeline.py` runs six sequential stages:

| Stage | What it checks |
|---|---|
| 1. Semantic | Nodes exist, edge references are valid, category-specific requirements met |
| 2. Graph | Connectivity, isolated nodes, self-loops |
| 3. Geometric | Node bounding-box overlaps after layout |
| 4. Typography | Font availability, compiler presence |
| 5. Compilation | Actual pdflatex / remote compile attempt |
| 6. Auto-repair | Granite analyses compilation error log and produces corrected TikZ |

Repair iterations are capped at `MAX_REPAIR_ATTEMPTS` (default: 3).
The pipeline never claims validation passed unless the checks were actually performed.

---

## 11. Local Setup

### Prerequisites

- Python 3.11+
- Node.js 20+
- TeX Live (or MiKTeX) with `pdflatex` on `PATH`
- IBM watsonx.ai account with API key and project ID

### Backend

```bash
cd tikz-diagram-generator/backend
python -m venv .venv
# Windows:  .venv\Scripts\activate
# Linux/Mac: source .venv/bin/activate
pip install -r requirements.txt

# Copy and fill in credentials
cp ../.env.example ../.env
# Edit .env: set WATSONX_APIKEY, WATSONX_PROJECT_ID

# Start the server
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend

```bash
cd tikz-diagram-generator/frontend
npm install
# Configure NEXT_PUBLIC_BACKEND_URL in frontend/.env.local
echo "NEXT_PUBLIC_BACKEND_URL=http://localhost:8000" > .env.local
npm run dev
# Open http://localhost:3000
```

### Run tests (no LaTeX/Granite required)

```bash
cd tikz-diagram-generator
python -m pytest backend/tests/ -v
```

---

## 12. Vercel Deployment

The **Next.js frontend** deploys to Vercel.

The backend and LaTeX compilation **cannot** run on Vercel serverless functions due to
execution time limits and the inability to install TeX Live. Use a separately hosted worker
(see section 13) and point the frontend's rewrite rules at it.

```bash
# Set these in Vercel environment variables:
NEXT_PUBLIC_BACKEND_URL=https://your-worker.example.com
NEXT_PUBLIC_ACCESS_TOKEN=your-optional-token

# Edit vercel.json:
# Replace BACKEND_WORKER_URL with your actual worker URL
```

Deployment steps:
1. Fork / clone this repository.
2. Import the project in Vercel, set root directory to `frontend/`.
3. Add the environment variables above.
4. Deploy.

---

## 13. Worker Deployment

The backend worker handles all computationally intensive operations.
It can be deployed anywhere Docker is supported (Fly.io, Railway, AWS ECS, GCP Cloud Run, etc.).

```bash
cd tikz-diagram-generator/worker

# Build
docker build -f Dockerfile -t tikz-generator-worker ..

# Run locally
docker run -p 8000:8000 \
  -e WATSONX_APIKEY=your-key \
  -e WATSONX_PROJECT_ID=your-project \
  -e USE_FONTSPEC=false \
  tikz-generator-worker

# Production: set all .env variables as Docker environment variables or secrets
```

**Times New Roman in Docker**: The Dockerfile installs `texlive-fonts-recommended` and
`fonts-texgyre`. Times New Roman (the proprietary Microsoft font) requires a separate license.
To use it:
1. Obtain the font files legally.
2. Uncomment the COPY and fc-cache lines in the Dockerfile.
3. Set `USE_FONTSPEC=true` and `LATEX_COMPILER=lualatex`.

For open deployments without the font, set `USE_FONTSPEC=false` (uses mathptmx via pdflatex).

---

## 14. Testing

```bash
# All tests (no network or Granite calls required)
python -m pytest backend/tests/ -v

# Specific test files
python -m pytest backend/tests/test_conventions.py -v
python -m pytest backend/tests/test_ir_schema.py -v
python -m pytest backend/tests/test_geometry.py -v
python -m pytest backend/tests/test_tikz_generation.py -v
python -m pytest backend/tests/test_validation.py -v
python -m pytest backend/tests/test_history.py -v
```

The test suite covers:
- **Convention profiles**: All categories load; required shapes and styles present.
- **IR schema**: Pydantic validation, edge reference checking, UML members, round-trip.
- **Geometry**: Node dimensions, layout positions, overlap detection and resolution.
- **TikZ generation**: Document structure, node IDs, groups, UML multipart, quantum gates, ERD diamonds, edge styles.
- **Validation pipeline**: All six stages, repair invocation, overlap detection.
- **History service**: Push/undo/redo/clear/redo-after-new-action.

Integration tests requiring a live Granite connection or LaTeX compiler are marked with
`@pytest.mark.integration` and skipped in CI unless the required environment variables are set.

---

## 15. Known Limitations

1. **Times New Roman availability**: The font requires a separate license on Linux.
   The Docker image uses mathptmx (pdflatex) by default for portability.
   Set `USE_FONTSPEC=false` unless you have the font installed.

2. **Electrical and digital circuit symbols**: The `circuitikz` package provides
   the definitive electrical symbols. This version generates TikZ using the
   `circuits.ee.IEC` and `circuits.logic.IEC` built-in TikZ libraries, which
   have a smaller symbol set than CircuiTikZ. For production electrical diagrams,
   adding `circuitikz` support is recommended.

3. **Quantum circuit gates**: Multi-qubit gates (Toffoli, controlled-U) and
   barrier lines are generated as best-effort TikZ. Dedicated packages such as
   `quantikz` or `yquant` provide richer quantum-circuit notation. Integration
   with `quantikz` can be added by registering a new TikZ template in
   `backend/tikz/generator.py`.

4. **UML sequence diagrams**: Message timing, combined fragments (alt/opt/loop),
   and actor interaction frames require additional coordinate calculation that
   goes beyond the current layered layout. These generate a basic approximation.

5. **Research agent**: Depends on network access and the availability of search
   providers. DuckDuckGo is used by default and requires no API key, but may be
   rate-limited. SerpAPI or Brave Search are more reliable in production.

6. **History persistence**: The undo/redo stack is in-memory per worker process.
   On process restart, history is lost. For persistent history, configure Redis
   via the `REDIS_URL` environment variable and swap `HistoryService` for a
   Redis-backed implementation.

7. **Concurrent sessions**: The in-memory diagram store (`_diagram_store` in
   `routes.py`) is per-process. In a multi-worker deployment, use shared storage
   (Redis, S3, or a database) for diagram retrieval.

8. **Async job handling**: For very long generation tasks (large diagrams,
   research + compilation), the current implementation is synchronous. An async
   job queue (Celery + Redis or similar) can be added by wrapping
   `DiagramService.generate()` in a background task.

---

## Environment Variables Reference

| Variable | Default | Description |
|---|---|---|
| `WATSONX_URL` | `https://us-south.ml.cloud.ibm.com` | watsonx.ai regional endpoint |
| `WATSONX_APIKEY` | — | **Required**. IBM Cloud API key |
| `WATSONX_PROJECT_ID` | — | **Required**. watsonx.ai project ID |
| `GRANITE_CODE_MODEL_ID` | `ibm/granite-4-h-small` | Granite model for code/IR |
| `GRANITE_VISION_MODEL_ID` | `meta-llama/llama-4-maverick-17b-128e-instruct-fp8` | Vision model for sketches |
| `USE_FONTSPEC` | `false` | `true` = XeLaTeX + Times New Roman; `false` = pdflatex + mathptmx |
| `LATEX_COMPILER` | `pdflatex` | Local compiler to try first |
| `MAX_REPAIR_ATTEMPTS` | `3` | Maximum Granite-assisted repair iterations |
| `SEARCH_PROVIDER` | `duckduckgo` | `duckduckgo`, `serpapi`, or `brave` |
| `SEARCH_API_KEY` | — | Required for SerpAPI or Brave |
| `ACCESS_TOKEN` | — | Optional API auth token |
| `LOG_LEVEL` | `INFO` | Python logging level |

See `.env.example` for the complete list.
