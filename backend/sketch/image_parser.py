"""
Sketch / image interpretation pipeline.

Accepts a base64-encoded PNG and produces a DiagramIR.
Uses the vision-capable model.
"""
from __future__ import annotations

import logging
from typing import Any

from backend.agents.granite_client import GraniteClient
from backend.agents.intent_agent import IntentAgent, _extract_json, _SYSTEM_PROMPT

logger = logging.getLogger(__name__)

_SKETCH_VISION_PROMPT = (
    "You are analyzing a hand-drawn sketch or screenshot of a technical diagram.\n\n"
    + _SYSTEM_PROMPT
    + "\n\nExtract all shapes, containers, labels, and arrows visible in the image. "
    "Produce the JSON IR described above."
)


class SketchInterpreter:
    """Interprets uploaded images using the vision model."""

    def __init__(self, client: GraniteClient) -> None:
        self._client = client
        self._intent = IntentAgent(client)

    def interpret(self, image_b64: str, additional_notes: str = "") -> Any:
        """
        Returns a DiagramIR extracted from the uploaded image.
        additional_notes can carry supplemental text from the user.
        """
        text_prompt = (
            "Extract all boxes, containers, and arrows from this sketch.\n"
            f"Additional notes: {additional_notes}\n\n"
            "Respond ONLY with the valid JSON object:"
        )
        try:
            raw = self._client.chat_with_image(
                _SKETCH_VISION_PROMPT,
                text_prompt,
                image_b64,
            )
            data = _extract_json(raw)
            return self._intent._dict_to_ir(data, source_prompt=additional_notes)
        except Exception as exc:
            logger.error("SketchInterpreter failed: %s", exc)
            raise
