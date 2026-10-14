"""Helpers to robustly pull a JSON object out of LLM output."""

from __future__ import annotations

import json
import re
from typing import Any

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)


def extract_json(text: str) -> Any:
    """Parse JSON from raw model output, tolerating markdown fences and surrounding prose.

    Raises:
        ValueError: if no JSON object/array can be decoded.
    """
    if not text or not text.strip():
        raise ValueError("empty model output")

    candidates = [text.strip()]
    candidates.extend(m.strip() for m in _FENCE_RE.findall(text))

    decoder = json.JSONDecoder()
    for candidate in candidates:
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass
        for index, char in enumerate(candidate):
            if char in "{[":
                try:
                    value, _ = decoder.raw_decode(candidate, index)
                    return value
                except json.JSONDecodeError:
                    continue
    raise ValueError("no valid JSON found in model output")
