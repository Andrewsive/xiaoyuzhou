from __future__ import annotations

import json
from typing import Any

import requests


class OpenAICompatibleClient:
    def __init__(self, *, api_key: str, base_url: str):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")

    def chat(self, *, model: str, messages: list[dict[str, str]], temperature: float = 0.2) -> str:
        response = requests.post(
            f"{self.base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": messages,
                "temperature": temperature,
            },
            timeout=120,
        )
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]

    def embeddings(self, *, model: str, texts: list[str]) -> list[list[float]]:
        response = requests.post(
            f"{self.base_url}/embeddings",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={"model": model, "input": texts},
            timeout=120,
        )
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
