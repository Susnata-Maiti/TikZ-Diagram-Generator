"""
LaTeX compiler and PDF/PNG renderer.

Strategy:
1. Try local pdflatex / lualatex / xelatex.
2. Fall back to texlive.net online compiler.
3. Extract compilation errors for the repair agent.
"""
from __future__ import annotations

import base64
import logging
import os
import shutil
import subprocess
import tempfile
from io import BytesIO
from typing import Optional

import pymupdf as fitz
from PIL import Image

from backend.config import get_settings

logger = logging.getLogger(__name__)


class CompilationResult:
    __slots__ = ("success", "pdf_bytes", "png_image", "status", "log")

    def __init__(
        self,
        success: bool,
        pdf_bytes: Optional[bytes],
        png_image: Optional[Image.Image],
        status: str,
        log: str,
    ) -> None:
        self.success = success
        self.pdf_bytes = pdf_bytes
        self.png_image = png_image
        self.status = status
        self.log = log

    @property
    def pdf_b64(self) -> Optional[str]:
        if self.pdf_bytes:
            return base64.b64encode(self.pdf_bytes).decode()
        return None

    @property
    def png_b64(self) -> Optional[str]:
        if self.png_image:
            buf = BytesIO()
            self.png_image.save(buf, format="PNG")
            return base64.b64encode(buf.getvalue()).decode()
        return None


class LatexCompiler:
    """Compiles standalone LaTeX/TikZ to PDF and PNG."""

    def __init__(self) -> None:
        self.cfg = get_settings()

    def compile(self, tex_code: str) -> CompilationResult:
        """Try local compiler first, fall back to texlive.net."""
        compiler = self._detect_local_compiler()
        if compiler:
            result = self._compile_local(tex_code, compiler)
            if result.success:
                return result
            # Local compile failed — return the error so the repair agent can fix it
            logger.warning("Local compile failed: %s", result.status[:300])
            return result

        return self._compile_remote(tex_code)

    # ── Local compilation ─────────────────────────────────────────────────────

    def _detect_local_compiler(self) -> Optional[str]:
        cfg = self.cfg
        preferred = cfg.latex_compiler
        for name in [preferred, "lualatex", "xelatex", "pdflatex"]:
            if shutil.which(name):
                return name
        return None

    def _compile_local(self, tex_code: str, compiler: str) -> CompilationResult:
        cfg = self.cfg
        with tempfile.TemporaryDirectory() as tmpdir:
            tex_path = os.path.join(tmpdir, "diagram.tex")
            pdf_path = os.path.join(tmpdir, "diagram.pdf")
            with open(tex_path, "w", encoding="utf-8") as f:
                f.write(tex_code)

            proc = subprocess.run(
                [compiler, "-interaction=nonstopmode", "-halt-on-error", "diagram.tex"],
                cwd=tmpdir,
                capture_output=True,
                text=True,
                timeout=60,
            )
            log_text = (proc.stdout or "") + (proc.stderr or "")

            if proc.returncode == 0 and os.path.exists(pdf_path):
                with open(pdf_path, "rb") as f:
                    pdf_bytes = f.read()
                img = self._pdf_to_png(pdf_bytes)
                return CompilationResult(
                    success=True,
                    pdf_bytes=pdf_bytes,
                    png_image=img,
                    status=f"Compiled successfully via {compiler}.",
                    log=log_text[-3000:],
                )
            else:
                return CompilationResult(
                    success=False,
                    pdf_bytes=None,
                    png_image=None,
                    status=f"Compilation failed ({compiler}).",
                    log=log_text[-3000:],
                )

    # ── Remote fallback ───────────────────────────────────────────────────────

    def _compile_remote(self, tex_code: str) -> CompilationResult:
        import requests  # lazy import to avoid hard dep when local works

        cfg = self.cfg
        try:
            files = {
                "filecontents[]": ("document.tex", tex_code),
                "filename[]": (None, "document.tex"),
                "engine": (None, "pdflatex"),
                "return": (None, "pdf"),
            }
            resp = requests.post(cfg.latex_fallback_url, files=files, timeout=45)
            if (
                resp.status_code == 200
                and resp.headers.get("Content-Type", "").startswith("application/pdf")
            ):
                pdf_bytes = resp.content
                img = self._pdf_to_png(pdf_bytes)
                return CompilationResult(
                    success=True,
                    pdf_bytes=pdf_bytes,
                    png_image=img,
                    status="Compiled successfully via texlive.net.",
                    log="",
                )
            log_text = resp.text if resp.text else f"HTTP {resp.status_code}"
            error_lines = [
                line.strip() for line in log_text.splitlines()
                if line.startswith("!") or "Error" in line or "Fatal" in line
            ]
            detail = f" ({error_lines[0]})" if error_lines else ""
            return CompilationResult(
                success=False,
                pdf_bytes=None,
                png_image=None,
                status=f"Remote compilation failed{detail}",
                log=log_text[-3000:],
            )
        except Exception as exc:
            return CompilationResult(
                success=False,
                pdf_bytes=None,
                png_image=None,
                status=f"Remote compiler unreachable: {exc}",
                log=str(exc),
            )

    # ── PDF → PNG ─────────────────────────────────────────────────────────────

    def _pdf_to_png(self, pdf_bytes: bytes) -> Optional[Image.Image]:
        try:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            page = doc.load_page(0)
            pix = page.get_pixmap(dpi=self.cfg.preview_dpi)
            return Image.open(BytesIO(pix.tobytes("png")))
        except Exception as exc:
            logger.error("PDF→PNG failed: %s", exc)
            return None
