from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv
from ruamel.yaml import YAML

from .models import PodcastDefinition
from .utils import ensure_directory, extract_podcast_id


@dataclass(slots=True)
class DatabaseConfig:
    path: str = "data/pipeline.db"


@dataclass(slots=True)
class RssHubConfig:
    base_url: str = "https://rsshub.app"
    user_agent: str = "Mozilla/5.0"


@dataclass(slots=True)
class DashScopeAsrConfig:
    provider: str = "auto"
    api_key_env: str = "DASHSCOPE_API_KEY"
    base_url: str = "https://dashscope.aliyuncs.com"
    model: str = "fun-asr"
    whisper_model: str = "base"
    poll_interval_seconds: int = 5
    timeout_seconds: int = 7200
    diarization_enabled: bool = True
    speaker_count: int | None = None
    language_hints: list[str] = field(default_factory=lambda: ["zh", "en"])


@dataclass(slots=True)
class CleanerConfig:
    provider: str = "auto"
    api_key_env: str = "LLM_API_KEY"
    base_url_env: str = "LLM_BASE_URL"
    model_env: str = "LLM_MODEL"
    default_base_url: str = "https://api.openai.com/v1"
    default_model: str = "gpt-4o-mini"
    temperature: float = 0.2
    max_input_chars: int = 3000


@dataclass(slots=True)
class EmbeddingConfig:
    provider: str = "auto"
    api_key_env: str = "EMBEDDING_API_KEY"
    base_url_env: str = "EMBEDDING_BASE_URL"
    model_env: str = "EMBEDDING_MODEL"
    default_base_url: str = "https://api.openai.com/v1"
    default_model: str = "text-embedding-3-small"
    collection_name: str = "podcast_knowledge"
    persist_path: str = "data/vector/chroma"


@dataclass(slots=True)
class StorageConfig:
    base_dir: str = "data"
    raw_rss_dir: str = "raw/rss"
    audio_dir: str = "audio"
    transcript_dir: str = "transcripts"
    cleaned_dir: str = "cleaned"
    logs_dir: str = "logs"


@dataclass(slots=True)
class AppConfig:
    database: DatabaseConfig
    rsshub: RssHubConfig
    asr: DashScopeAsrConfig
    cleaner: CleanerConfig
    embedding: EmbeddingConfig
    storage: StorageConfig
    podcasts: list[PodcastDefinition]
    workspace_root: Path

    @property
    def database_path(self) -> Path:
        return self.workspace_root / self.database.path

    @property
    def storage_base_path(self) -> Path:
        return self.workspace_root / self.storage.base_dir

    @property
    def raw_rss_path(self) -> Path:
        return self.storage_base_path / self.storage.raw_rss_dir

    @property
    def audio_path(self) -> Path:
        return self.storage_base_path / self.storage.audio_dir

    @property
    def transcript_path(self) -> Path:
        return self.storage_base_path / self.storage.transcript_dir

    @property
    def cleaned_path(self) -> Path:
        return self.storage_base_path / self.storage.cleaned_dir

    @property
    def logs_path(self) -> Path:
        return self.storage_base_path / self.storage.logs_dir

    @property
    def vector_path(self) -> Path:
        return self.workspace_root / self.embedding.persist_path

    def ensure_directories(self) -> None:
        for path in [
            self.storage_base_path,
            self.raw_rss_path,
            self.audio_path,
            self.transcript_path,
            self.cleaned_path,
            self.logs_path,
            self.vector_path,
            self.database_path.parent,
        ]:
            ensure_directory(path)

    def cleaner_base_url(self) -> str:
        return os.getenv(self.cleaner.base_url_env, self.cleaner.default_base_url).rstrip("/")

    def cleaner_model(self) -> str:
        return os.getenv(self.cleaner.model_env, self.cleaner.default_model)

    def embedding_base_url(self) -> str:
        return os.getenv(self.embedding.base_url_env, self.embedding.default_base_url).rstrip("/")

    def embedding_model(self) -> str:
        return os.getenv(self.embedding.model_env, self.embedding.default_model)


def _load_podcasts(raw_podcasts: list[dict]) -> list[PodcastDefinition]:
    podcasts: list[PodcastDefinition] = []
    for item in raw_podcasts:
        source_url = item["source_url"].strip()
        podcast_id = item.get("podcast_id") or extract_podcast_id(source_url)
        podcasts.append(
            PodcastDefinition(
                podcast_id=podcast_id,
                display_name=item.get("display_name", podcast_id),
                source_url=source_url,
                rss_url=item.get("rss_url"),
                enabled=bool(item.get("enabled", True)),
            )
        )
    return podcasts


def load_config(config_path: Path) -> AppConfig:
    load_dotenv(config_path.parent / ".env")
    yaml = YAML(typ="safe")
    data = yaml.load(config_path.read_text(encoding="utf-8")) or {}
    workspace_root = config_path.parent.resolve()

    return AppConfig(
        database=DatabaseConfig(**data.get("database", {})),
        rsshub=RssHubConfig(**data.get("rsshub", {})),
        asr=DashScopeAsrConfig(**data.get("asr", {})),
        cleaner=CleanerConfig(**data.get("cleaner", {})),
        embedding=EmbeddingConfig(**data.get("embedding", {})),
        storage=StorageConfig(**data.get("storage", {})),
        podcasts=_load_podcasts(data.get("podcasts", [])),
        workspace_root=workspace_root,
    )
