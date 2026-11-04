"""
Central configuration loaded from environment variables.
Never hardcode credentials here.
"""
from __future__ import annotations

import os
from pathlib import Path
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict

_ROOT_ENV = Path(__file__).resolve().parent.parent / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ROOT_ENV) if _ROOT_ENV.exists() else ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── IBM watsonx.ai ────────────────────────────────────────────────────────
    watsonx_url: str = "https://us-south.ml.cloud.ibm.com"
    watsonx_apikey: str = ""
    watsonx_project_id: str = ""

    # Granite model IDs (match reference notebook)
    granite_code_model_id: str = "ibm/granite-4-h-small"
    granite_vision_model_id: str = "meta-llama/llama-4-maverick-17b-128e-instruct-fp8"

    # Model generation params
    granite_max_tokens: int = 4096
    granite_temperature: float = 0.05
    vision_max_tokens: int = 2048
    vision_temperature: float = 0.1

    # ── Application ───────────────────────────────────────────────────────────
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    debug: bool = False

    # Optional access-token guard for the public endpoint
    access_token: str = ""

    # ── Storage ───────────────────────────────────────────────────────────────
    # Local artifact output directory (used in dev; swap for S3 path in prod)
    artifact_dir: str = "artifacts"

    # ── Research ──────────────────────────────────────────────────────────────
    # Optional SerpAPI / Brave Search key for the research agent
    search_api_key: str = ""
    search_provider: str = "duckduckgo"   # "duckduckgo" | "serpapi" | "brave"
    research_max_results: int = 5

    # ── Layout engine ─────────────────────────────────────────────────────────
    layout_node_width_cm: float = 3.0
    layout_node_height_cm: float = 1.2
    layout_h_gap_cm: float = 2.6
    layout_v_gap_cm: float = 1.8
    layout_padding_cm: float = 0.5
    layout_container_inner_sep_cm: float = 0.6

    # ── Compiler ──────────────────────────────────────────────────────────────
    latex_compiler: str = "pdflatex"   # "pdflatex" | "lualatex" | "xelatex"
    latex_fallback_url: str = "https://texlive.net/cgi-bin/latexcgi"
    preview_dpi: int = 220
    max_repair_attempts: int = 3

    # ── Typography ────────────────────────────────────────────────────────────
    preferred_font: str = "Times New Roman"
    fallback_font: str = "TeX Gyre Termes"
    use_fontspec: bool = False  # True only for lualatex/xelatex; pdflatex uses mathptmx

    # ── Redis (optional – used for async job queue in prod) ───────────────────
    redis_url: str = ""

    # ── Logging ───────────────────────────────────────────────────────────────
    log_level: str = "INFO"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
