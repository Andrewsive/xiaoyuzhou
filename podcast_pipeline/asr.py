from __future__ import annotations

import json
import os
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

    def transcribe_episode(self, episode: dict, output_path: Path) -> Path:
        audio_url = episode["audio_url"]
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


class WhisperAsrProvider:
    _model_cache: dict[str, object] = {}

    def __init__(self, config: AppConfig):
        self.config = config

    def transcribe_episode(self, episode: dict, output_path: Path) -> Path:
        audio_path = episode.get("audio_path")
        if not audio_path:
            raise RuntimeError("audio_path is required for local Whisper transcription")

        import whisper

        model_name = self.config.asr.whisper_model
        model = self._model_cache.get(model_name)
        if model is None:
            model = whisper.load_model(model_name)
            self._model_cache[model_name] = model

        if os.name == "nt" and not os.getenv("PATH", "").lower().count("ffmpeg"):
            ffmpeg_root = r"C:\Users\yichen\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.1-full_build\bin"
            os.environ["PATH"] = os.environ.get("PATH", "") + os.pathsep + ffmpeg_root

        result = model.transcribe(str(audio_path), language="zh", fp16=False)
        payload = {
            "task": {"output": {"task_status": "SUCCEEDED", "results": [{"subtask_status": "SUCCEEDED"}]}},
            "files": [
                {
                    "file_url": episode["audio_url"],
                    "transcription_url": "",
                    "payload": {
                        "transcripts": [
                            {
                                "sentences": [
                                    {
                                        "sentence_id": segment.get("id", index),
                                        "begin_time": int(segment.get("start", 0) * 1000),
                                        "end_time": int(segment.get("end", 0) * 1000),
                                        "text": segment.get("text", "").strip(),
                                        "speaker_id": "whisper",
                                    }
                                    for index, segment in enumerate(result.get("segments", []), start=1)
                                    if segment.get("text", "").strip()
                                ]
                            }
                        ]
                    },
                }
            ],
        }
        output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return output_path


def build_asr_provider(config: AppConfig):
    provider = config.asr.provider.lower()
    has_dashscope_key = bool(os.getenv(config.asr.api_key_env, "").strip())
    if provider == "whisper" or (provider == "auto" and not has_dashscope_key):
        return WhisperAsrProvider(config)
    return DashScopeAsrProvider(config)
