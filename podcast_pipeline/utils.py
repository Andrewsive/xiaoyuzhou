from __future__ import annotations

import hashlib
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse


XIAOYUZHOU_PODCAST_PATTERN = re.compile(r"/podcast/([a-zA-Z0-9]+)")
XIAOYUZHOU_EPISODE_PATTERN = re.compile(r"/episode/([a-zA-Z0-9]+)")


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def ensure_directory(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def sha1_text(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()


def extract_podcast_id(source_url: str) -> str:
    match = XIAOYUZHOU_PODCAST_PATTERN.search(source_url)
    if not match:
        raise ValueError(f"Could not extract Xiaoyuzhou podcast id from {source_url}")
    return match.group(1)


def extract_episode_id(source_url: str) -> str:
    match = XIAOYUZHOU_EPISODE_PATTERN.search(source_url)
    if not match:
        raise ValueError(f"Could not extract Xiaoyuzhou episode id from {source_url}")
    return match.group(1)


def guess_extension_from_url(url: str, default: str = ".mp3") -> str:
    path = urlparse(url).path
    suffix = Path(path).suffix.lower()
    if suffix and len(suffix) <= 5:
        return suffix
    return default


def sanitize_collection_value(value: object) -> str | int | float | bool:
    if isinstance(value, (str, int, float, bool)):
        return value
    if value is None:
        return ""
    if isinstance(value, (list, tuple, set)):
        return ", ".join(str(item) for item in value)
    return str(value)


def getenv_required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Environment variable {name} is required")
    return value
