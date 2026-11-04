"""
Thin wrapper around ibm_watsonx_ai ModelInference.

Provides:
- chat()   – structured chat messages → str
- repair() – convenience call reusing TIKZ_REPAIR_SYSTEM prompt
- Retry logic with exponential back-off
- No API key logging
"""
from __future__ import annotations

import logging
import time
from typing import Any

from ibm_watsonx_ai import Credentials
from ibm_watsonx_ai.foundation_models import ModelInference

from backend.config import get_settings

logger = logging.getLogger(__name__)


def _build_model(model_id: str, max_tokens: int, temperature: float) -> ModelInference:
    cfg = get_settings()
    if not cfg.watsonx_apikey:
        raise RuntimeError(
            "WATSONX_APIKEY is not set. "
            "Export it as an environment variable or add it to .env."
        )
    credentials = Credentials(url=cfg.watsonx_url, api_key=cfg.watsonx_apikey)
    return ModelInference(
        model_id=model_id,
        credentials=credentials,
        project_id=cfg.watsonx_project_id,
        params={"max_tokens": max_tokens, "temperature": temperature},
    )


class GraniteClient:
    """
    Singleton-style client.  Instantiate once at startup and share across agents.
    """

    def __init__(self) -> None:
        cfg = get_settings()
        self._code_model = _build_model(
            cfg.granite_code_model_id,
            cfg.granite_max_tokens,
            cfg.granite_temperature,
        )
        self._vision_model = _build_model(
            cfg.granite_vision_model_id,
            cfg.vision_max_tokens,
            cfg.vision_temperature,
        )
        logger.info(
            "GraniteClient ready | code=%s vision=%s project=%s…",
            cfg.granite_code_model_id,
            cfg.granite_vision_model_id,
            cfg.watsonx_project_id[:8] if cfg.watsonx_project_id else "?",
        )

    # ── public helpers ────────────────────────────────────────────────────────

    def chat(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        max_retries: int = 3,
        use_vision: bool = False,
    ) -> str:
        """Send a chat message and return the raw text response."""
        model = self._vision_model if use_vision else self._code_model
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        return self._call_with_retry(model, messages, max_retries=max_retries)

    def chat_with_image(
        self,
        system_prompt: str,
        text_prompt: str,
        image_b64: str,
        *,
        max_retries: int = 3,
    ) -> str:
        """Send a vision chat message with an inline base64 image."""
        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{image_b64}"},
                    },
                    {"type": "text", "text": text_prompt},
                ],
            },
        ]
        return self._call_with_retry(
            self._vision_model, messages, max_retries=max_retries
        )

    # ── internal ──────────────────────────────────────────────────────────────

    @staticmethod
    def _call_with_retry(
        model: ModelInference,
        messages: list[dict[str, Any]],
        *,
        max_retries: int,
    ) -> str:
        last_exc: Exception | None = None
        for attempt in range(max_retries):
            try:
                response = model.chat(messages=messages)
                return response["choices"][0]["message"]["content"]
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                wait = 2 ** attempt
                logger.warning(
                    "Granite call failed (attempt %d/%d): %s – retrying in %ds",
                    attempt + 1,
                    max_retries,
                    exc,
                    wait,
                )
                time.sleep(wait)
        # Final fallback: try generate_text
        try:
            combined = "\n\n".join(
                m["content"] if isinstance(m["content"], str) else str(m["content"])
                for m in messages
            )
            return model.generate_text(prompt=combined)
        except Exception as exc:
            raise RuntimeError(
                f"All {max_retries} Granite retries failed. Last error: {last_exc}"
            ) from exc
