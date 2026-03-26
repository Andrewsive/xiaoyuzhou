from __future__ import annotations

import json
import time
from pathlib import Path

import requests

from .config import AppConfig
from .utils import getenv_required


class DashScopeAsrProvider:
    def __init__(self, config: AppConfig):
        self.config = config
        self.api_key = getenv_required(config.asr.api_key_env)
        self.base_url = config.asr.base_url.rstrip("/")

    def transcribe_to_file(self, *, audio_url: str, output_path: Path) -> Path:
        task_id = self._submit_task(audio_url)
        task_payload = self._wait_for_completion(task_id)
        results = task_payload["output"]["results"]
        files: list[dict] = []
        for result in results:
            if result.get("subtask_status") != "SUCCEEDED":
                raise RuntimeError(
                    f"DashScope subtask failed: {result.get('code', 'UNKNOWN')} {result.get('message', '')}"
                )
            transcription_url = result["transcription_url"]
            transcript_response = requests.get(transcription_url, timeout=60)
            transcript_response.raise_for_status()
            files.append(
                {
                    "file_url": result.get("file_url", audio_url),
                    "transcription_url": transcription_url,
                    "payload": transcript_response.json(),
                }
            )
        output_path.write_text(
            json.dumps({"task": task_payload, "files": files}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return output_path

    def _submit_task(self, audio_url: str) -> str:
        parameters: dict[str, object] = {
            "channel_id": [0],
            "language_hints": self.config.asr.language_hints,
            "diarization_enabled": self.config.asr.diarization_enabled,
        }
        if self.config.asr.speaker_count:
            parameters["speaker_count"] = self.config.asr.speaker_count
        response = requests.post(
            f"{self.base_url}/api/v1/services/audio/asr/transcription",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "X-DashScope-Async": "enable",
            },
            json={
                "model": self.config.asr.model,
                "input": {"file_urls": [audio_url]},
                "parameters": parameters,
            },
            timeout=60,
        )
        response.raise_for_status()
        return response.json()["output"]["task_id"]

    def _wait_for_completion(self, task_id: str) -> dict:
        started = time.time()
        while True:
            if time.time() - started > self.config.asr.timeout_seconds:
                raise TimeoutError(f"DashScope task {task_id} timed out")
            response = requests.post(
                f"{self.base_url}/api/v1/tasks/{task_id}",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    "X-DashScope-Async": "enable",
                },
                timeout=60,
            )
            response.raise_for_status()
            data = response.json()
            status = data["output"]["task_status"]
            if status == "SUCCEEDED":
                return data
            if status in {"FAILED", "CANCELED"}:
                raise RuntimeError(f"DashScope task {task_id} ended with status {status}")
            time.sleep(self.config.asr.poll_interval_seconds)
