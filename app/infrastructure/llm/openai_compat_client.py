"""Minimal OpenAI-compatible chat completions client.

Works with providers exposing an OpenAI-like endpoint:
- POST {base_url}/v1/chat/completions
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx


@dataclass(frozen=True)
class OpenAICompatConfig:
    base_url: str
    api_key: str
    model: str
    timeout_s: float = 30.0


class OpenAICompatClient:
    def __init__(self, cfg: OpenAICompatConfig) -> None:
        self._cfg = cfg

    def chat_completion_json(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int,
    ) -> dict:
        url = self._cfg.base_url.rstrip("/") + "/v1/chat/completions"
        headers = {"Content-Type": "application/json"}
        if self._cfg.api_key:
            headers["Authorization"] = f"Bearer {self._cfg.api_key}"
        payload = {
            "model": self._cfg.model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_tokens": int(max_tokens),
            "response_format": {"type": "json_object"},
        }
        with httpx.Client(timeout=self._cfg.timeout_s) as client:
            r = client.post(url, headers=headers, json=payload)
            r.raise_for_status()
            return r.json()

