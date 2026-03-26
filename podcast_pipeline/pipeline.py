from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .asr import DashScopeAsrProvider
from .cleaner import TranscriptCleaner
from .config import AppConfig
from .db import (
    STATUS_CLEANED,
    STATUS_DISCOVERED,
    STATUS_DOWNLOADED,
    STATUS_FAILED_RETRYABLE,
    STATUS_INDEXED,
    STATUS_TRANSCRIBED,
    PipelineDB,
)
from .downloader import AudioDownloader
from .feed_source import RSSHubSource
from .indexer import VectorIndexer
from .utils import ensure_directory, utc_now_iso


class PipelineRunner:
    def __init__(self, config: AppConfig):
        self.config = config
        self.config.ensure_directories()
        self.db = PipelineDB(config.database_path)
        self.db.init_schema()
        self.source = RSSHubSource(config)
        self.downloader = AudioDownloader(config.audio_path)

    def close(self) -> None:
        self.db.close()

    def preflight(self) -> dict[str, Any]:
        self.config.ensure_directories()
        return {
            "database_path": str(self.config.database_path),
            "rsshub_base_url": self.config.rsshub.base_url,
            "rsshub_public_host_warning": "public rsshub.app may fail for Xiaoyuzhou routes"
            if "rsshub.app" in self.config.rsshub.base_url
            else "",
            "podcast_count": len(self.config.podcasts),
            "has_dashscope_key": bool(os.getenv(self.config.asr.api_key_env, "").strip()),
            "has_cleaner_key": bool(os.getenv(self.config.cleaner.api_key_env, "").strip()),
            "has_embedding_key": bool(os.getenv(self.config.embedding.api_key_env, "").strip()),
            "timestamp": utc_now_iso(),
        }

    def sync(self) -> dict[str, Any]:
        discovered = 0
        updated = 0
        errors: list[dict[str, str]] = []
        for podcast in self.config.podcasts:
            if not podcast.enabled:
                continue
            try:
                rss_url, episodes = self.source.fetch_feed(podcast)
                self.db.upsert_podcast(podcast, rss_url)
                for episode in episodes:
                    existing = None
                    try:
                        existing = self.db.get_episode(episode.episode_id)
                    except KeyError:
                        pass
                    self.db.upsert_episode(episode)
                    if existing is None:
                        discovered += 1
                    else:
                        updated += 1
            except Exception as exc:
                errors.append({"podcast_id": podcast.podcast_id, "error": str(exc)})
        return {"discovered": discovered, "updated": updated, "errors": errors}

    def download_pending(self) -> int:
        count = 0
        for episode in self.db.get_episodes_by_status([STATUS_DISCOVERED]):
            run_id = self.db.mark_stage_started(episode["episode_id"], "download")
            try:
                audio_path = self.downloader.download(
                    podcast_id=episode["podcast_id"],
                    episode_id=episode["episode_id"],
                    audio_url=episode["audio_url"],
                )
                self.db.mark_stage_finished(
                    run_id,
                    episode["episode_id"],
                    "download",
                    STATUS_DOWNLOADED,
                    extra_fields={"audio_path": str(audio_path)},
                )
                count += 1
            except Exception as exc:
                self.db.mark_stage_finished(
                    run_id,
                    episode["episode_id"],
                    "download",
                    STATUS_FAILED_RETRYABLE,
                    last_error=str(exc),
                )
        return count

    def transcribe_pending(self) -> int:
        count = 0
        provider = DashScopeAsrProvider(self.config)
        for episode in self.db.get_episodes_by_status([STATUS_DOWNLOADED]):
            run_id = self.db.mark_stage_started(episode["episode_id"], "transcribe")
            output_dir = ensure_directory(self.config.transcript_path / episode["podcast_id"])
            output_path = output_dir / f"{episode['episode_id']}.json"
            try:
                provider.transcribe_to_file(audio_url=episode["audio_url"], output_path=output_path)
                self.db.mark_stage_finished(
                    run_id,
                    episode["episode_id"],
                    "transcribe",
                    STATUS_TRANSCRIBED,
                    extra_fields={"transcript_path": str(output_path)},
                )
                count += 1
            except Exception as exc:
                self.db.mark_stage_finished(
                    run_id,
                    episode["episode_id"],
                    "transcribe",
                    STATUS_FAILED_RETRYABLE,
                    last_error=str(exc),
                )
        return count

    def clean_pending(self) -> int:
        count = 0
        cleaner = TranscriptCleaner(self.config)
        for episode in self.db.get_episodes_by_status([STATUS_TRANSCRIBED]):
            run_id = self.db.mark_stage_started(episode["episode_id"], "clean")
            output_dir = ensure_directory(self.config.cleaned_path / episode["podcast_id"])
            jsonl_path = output_dir / f"{episode['episode_id']}.jsonl"
            md_path = output_dir / f"{episode['episode_id']}.md"
            try:
                cleaner.clean_to_files(
                    transcript_path=Path(episode["transcript_path"]),
                    jsonl_output_path=jsonl_path,
                    md_output_path=md_path,
                )
                self.db.mark_stage_finished(
                    run_id,
                    episode["episode_id"],
                    "clean",
                    STATUS_CLEANED,
                    extra_fields={
                        "cleaned_jsonl_path": str(jsonl_path),
                        "summary_md_path": str(md_path),
                    },
                )
                count += 1
            except Exception as exc:
                self.db.mark_stage_finished(
                    run_id,
                    episode["episode_id"],
                    "clean",
                    STATUS_FAILED_RETRYABLE,
                    last_error=str(exc),
                )
        return count

    def index_pending(self) -> int:
        count = 0
        indexer = VectorIndexer(self.config)
        for episode in self.db.get_episodes_by_status([STATUS_CLEANED]):
            run_id = self.db.mark_stage_started(episode["episode_id"], "index")
            try:
                indexed_count = indexer.index_episode(
                    episode=dict(episode),
                    cleaned_jsonl_path=Path(episode["cleaned_jsonl_path"]),
                )
                self.db.mark_stage_finished(
                    run_id,
                    episode["episode_id"],
                    "index",
                    STATUS_INDEXED,
                    extra_fields={"indexed_at": utc_now_iso(), "content_hash": str(indexed_count)},
                )
                count += 1
            except Exception as exc:
                self.db.mark_stage_finished(
                    run_id,
                    episode["episode_id"],
                    "index",
                    STATUS_FAILED_RETRYABLE,
                    last_error=str(exc),
                )
        return count

    def retry_failed(self) -> int:
        retried = 0
        for episode in self.db.get_failed_retryable():
            stage = episode["last_stage"] or ""
            target_status = {
                "download": STATUS_DISCOVERED,
                "transcribe": STATUS_DOWNLOADED,
                "clean": STATUS_TRANSCRIBED,
                "index": STATUS_CLEANED,
            }.get(stage)
            if target_status:
                self.db.reset_failed_episode(episode["episode_id"], target_status)
                retried += 1
        return retried

    def run_once(self) -> dict[str, int]:
        result = self.sync()
        result["downloaded"] = self.download_pending()
        result["transcribed"] = self.transcribe_pending()
        result["cleaned"] = self.clean_pending()
        result["indexed"] = self.index_pending()
        return result

    def search(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        indexer = VectorIndexer(self.config)
        return indexer.search(query=query, top_k=top_k)

    def stats(self) -> dict[str, Any]:
        return {
            "counts": self.db.podcast_counts(),
            "database_path": str(self.config.database_path),
            "vector_path": str(self.config.vector_path),
        }

    def dump_json(self, payload: dict[str, Any]) -> str:
        return json.dumps(payload, ensure_ascii=False, indent=2)
