"""
FastAPI route handlers.

Endpoints:
  POST /api/diagram/generate
  POST /api/diagram/refine
  POST /api/diagram/validate
  POST /api/diagram/sketch
  POST /api/research
  POST /api/diagram/undo
  POST /api/diagram/redo
  GET  /api/diagram/{diagram_id}
  GET  /api/diagram/{diagram_id}/download
  GET  /api/health
"""
from __future__ import annotations

import base64
import logging
import time
from typing import Any, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Body
from fastapi.responses import Response
from pydantic import BaseModel, Field

from backend.config import get_settings
from backend.services.diagram_service import DiagramService
from backend.services.history_service import get_history_service

logger = logging.getLogger(__name__)
router = APIRouter()

# ── Shared service singleton ──────────────────────────────────────────────────

_service: Optional[DiagramService] = None


def _get_service() -> DiagramService:
    global _service
    if _service is None:
        _service = DiagramService()
    return _service


# ── Auth helper ───────────────────────────────────────────────────────────────

def _check_token(x_access_token: str = Header(default="")) -> None:
    cfg = get_settings()
    if cfg.access_token and x_access_token != cfg.access_token:
        raise HTTPException(status_code=401, detail="Missing or invalid x-access-token")


# ── Request / response models ──────────────────────────────────────────────────

class GenerateRequest(BaseModel):
    prompt: str
    enable_research: bool = False
    sketch_b64: Optional[str] = None   # base64 PNG, no data: prefix


class RefineRequest(BaseModel):
    prompt: str
    current_ir: dict[str, Any]
    current_tikz: str = ""
    session_id: str = ""


class ValidateRequest(BaseModel):
    tikz_code: str
    ir: Optional[dict[str, Any]] = None


class SketchRequest(BaseModel):
    sketch_b64: str    # base64 PNG
    notes: str = ""


class ResearchRequest(BaseModel):
    topic: str


class UndoRedoRequest(BaseModel):
    session_id: str
    current_ir: dict[str, Any]
    current_tikz: str = ""


# ── In-memory diagram store (swap for Redis/DB in production) ─────────────────

_diagram_store: dict[str, dict[str, Any]] = {}


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/health")
def health():
    return {"status": "ok", "timestamp": time.time()}


@router.post("/diagram/generate", dependencies=[Depends(_check_token)])
def generate_diagram(req: GenerateRequest, svc: DiagramService = Depends(_get_service)):
    if not req.prompt.strip() and not req.sketch_b64:
        raise HTTPException(status_code=400, detail="prompt or sketch_b64 is required")
    result = svc.generate(
        prompt=req.prompt,
        sketch_b64=req.sketch_b64,
        enable_research=req.enable_research,
    )
    data = result.to_dict()
    _diagram_store[result.diagram_id] = data
    return data


@router.post("/diagram/refine", dependencies=[Depends(_check_token)])
def refine_diagram(req: RefineRequest, svc: DiagramService = Depends(_get_service)):
    hist = get_history_service()
    if req.session_id:
        hist.push(req.session_id, req.current_ir, req.current_tikz)

    result = svc.refine(
        current_ir_dict=req.current_ir,
        instruction=req.prompt,
        current_tikz=req.current_tikz,
    )
    data = result.to_dict()
    _diagram_store[result.diagram_id] = data
    return data


@router.post("/diagram/validate", dependencies=[Depends(_check_token)])
def validate_diagram(req: ValidateRequest, svc: DiagramService = Depends(_get_service)):
    from backend.validation.pipeline import ValidationPipeline
    from backend.ir.schema import DiagramIR
    pipeline = ValidationPipeline()

    results = {}
    if req.ir:
        ir = DiagramIR.from_dict(req.ir)
        results["semantic"] = pipeline.validate_semantic(ir).model_dump()
        results["graph"] = pipeline.validate_graph(ir).model_dump()
        results["geometry"] = pipeline.validate_geometry(ir).model_dump()

    results["typography"] = pipeline.validate_typography().model_dump()

    if req.tikz_code:
        results["compilation"] = pipeline.validate_compilation(req.tikz_code).model_dump()

    passed = all(v.get("passed", True) for v in results.values())
    return {"passed": passed, "stages": results}


@router.post("/diagram/sketch", dependencies=[Depends(_check_token)])
def interpret_sketch(req: SketchRequest, svc: DiagramService = Depends(_get_service)):
    result = svc.generate(prompt=req.notes, sketch_b64=req.sketch_b64)
    data = result.to_dict()
    _diagram_store[result.diagram_id] = data
    return data


@router.post("/research", dependencies=[Depends(_check_token)])
def research_topic(req: ResearchRequest, svc: DiagramService = Depends(_get_service)):
    ctx = svc.research_topic(req.topic)
    return {
        "query": ctx.query,
        "technical_summary": ctx.technical_summary,
        "component_list": ctx.component_list,
        "connection_notes": ctx.connection_notes,
        "recommended_diagram_prompt": ctx.recommended_diagram_prompt,
        "sources": [{"url": s.url, "title": s.title} for s in ctx.results],
    }


@router.post("/diagram/undo", dependencies=[Depends(_check_token)])
def undo(req: UndoRedoRequest, svc: DiagramService = Depends(_get_service)):
    if not req.session_id:
        raise HTTPException(status_code=400, detail="session_id required for undo")
    hist = get_history_service()
    snapshot = hist.undo(req.session_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Nothing to undo")
    # Recompile the restored snapshot
    from backend.ir.schema import DiagramIR
    from backend.compiler.latex_compiler import LatexCompiler
    ir = DiagramIR.from_dict(snapshot["ir"])
    tikz = snapshot["tikz"]
    compiled = LatexCompiler().compile(tikz)
    return {
        "diagram_id": ir.id,
        "ir": snapshot["ir"],
        "tikz_code": tikz,
        "pdf_base64": compiled.pdf_b64,
        "png_base64": compiled.png_b64,
        "status": compiled.status,
        "agent_summary": "Reverted to previous state.",
    }


@router.post("/diagram/redo", dependencies=[Depends(_check_token)])
def redo(req: UndoRedoRequest, svc: DiagramService = Depends(_get_service)):
    if not req.session_id:
        raise HTTPException(status_code=400, detail="session_id required for redo")
    hist = get_history_service()
    snapshot = hist.redo(req.session_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Nothing to redo")
    from backend.ir.schema import DiagramIR
    from backend.compiler.latex_compiler import LatexCompiler
    ir = DiagramIR.from_dict(snapshot["ir"])
    tikz = snapshot["tikz"]
    compiled = LatexCompiler().compile(tikz)
    return {
        "diagram_id": ir.id,
        "ir": snapshot["ir"],
        "tikz_code": tikz,
        "pdf_base64": compiled.pdf_b64,
        "png_base64": compiled.png_b64,
        "status": compiled.status,
        "agent_summary": "Redone.",
    }


@router.get("/diagram/{diagram_id}", dependencies=[Depends(_check_token)])
def get_diagram(diagram_id: str):
    data = _diagram_store.get(diagram_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Diagram not found")
    return data


@router.get("/diagram/{diagram_id}/download", dependencies=[Depends(_check_token)])
def download_diagram(diagram_id: str, fmt: str = "pdf"):
    data = _diagram_store.get(diagram_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Diagram not found")

    if fmt == "tex":
        tikz = data.get("tikz_code", "")
        return Response(
            content=tikz.encode(),
            media_type="application/x-tex",
            headers={"Content-Disposition": f'attachment; filename="diagram_{diagram_id}.tex"'},
        )
    if fmt == "pdf" and data.get("pdf_base64"):
        pdf_bytes = base64.b64decode(data["pdf_base64"])
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="diagram_{diagram_id}.pdf"'},
        )
    if fmt == "png" and data.get("png_base64"):
        png_bytes = base64.b64decode(data["png_base64"])
        return Response(
            content=png_bytes,
            media_type="image/png",
            headers={"Content-Disposition": f'attachment; filename="diagram_{diagram_id}.png"'},
        )
    raise HTTPException(status_code=400, detail=f"Format '{fmt}' not available")
