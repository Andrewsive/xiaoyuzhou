from __future__ import annotations

import json
import time
from typing import Any

import requests


class OpenAICompatibleClient:
    def __init__(self, *, api_key: str, base_url: str):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = (20, 120)
        self.max_attempts = 3

    def _post(self, *, path: str, payload: dict[str, Any]) -> requests.Response:
        last_error: Exception | None = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                response = requests.post(
                    f"{self.base_url}{path}",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                    timeout=self.timeout,
                )
                response.raise_for_status()
                return response
            except requests.RequestException as exc:
                last_error = exc
                if attempt == self.max_attempts:
                    raise
                time.sleep(attempt * 2)
        assert last_error is not None
        raise last_error

    def chat(self, *, model: str, messages: list[dict[str, str]], temperature: float = 0.2) -> str:
        response = self._post(
            path="/chat/completions",
            payload={
                "model": model,
                "messages": messages,
                "temperature": temperature,
            },
        )
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]

    def embeddings(self, *, model: str, texts: list[str]) -> list[list[float]]:
        response = self._post(path="/embeddings", payload={"model": model, "input": texts})
        response.raise_for_status()
        payload = response.json()
        return [item["embedding"] for item in payload["data"]]


def parse_json_response(text: str) -> Any:
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if len(lines) >= 3:
            text = "\n".join(lines[1:-1])
    return json.loads(text)
