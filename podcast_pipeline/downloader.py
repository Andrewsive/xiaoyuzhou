from __future__ import annotations

from pathlib import Path

import requests

from .utils import ensure_directory, guess_extension_from_url


class AudioDownloader:
    def __init__(self, base_dir: Path):
        self.base_dir = base_dir

    def download(self, *, podcast_id: str, episode_id: str, audio_url: str) -> Path:
        target_dir = ensure_directory(self.base_dir / podcast_id)
        target_path = target_dir / f"{episode_id}{guess_extension_from_url(audio_url)}"
        if target_path.exists() and target_path.stat().st_size > 0:
            return target_path

        temp_path = target_path.with_suffix(target_path.suffix + ".part")
        with requests.get(audio_url, stream=True, timeout=60) as response:
            response.raise_for_status()
            with temp_path.open("wb") as handle:
                for chunk in response.iter_content(chunk_size=1024 * 512):
                    if chunk:
                        handle.write(chunk)
        temp_path.replace(target_path)
        return target_path
