"""
FastAPI application entry point.

Mounts all API routes and initialises shared services.
"""
from __future__ import annotations

import logging
import sys

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.config import get_settings
from backend.api.routes import router

# ── Logging ───────────────────────────────────────────────────────────────────

cfg = get_settings()
logging.basicConfig(
    level=cfg.log_level.upper(),
    format="%(asctime)s  %(levelname)-8s  %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="TikZ Diagram Generator",
    description=(
        "AI-powered TikZ diagram generator using IBM Granite on watsonx.ai. "
        "Transforms natural-language descriptions and sketches into publication-quality diagrams."
    ),
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],    # Restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")


@app.on_event("startup")
async def startup() -> None:
    logger.info(
        "TikZ Diagram Generator started | watsonx_url=%s | model=%s",
        cfg.watsonx_url,
        cfg.granite_code_model_id,
    )
