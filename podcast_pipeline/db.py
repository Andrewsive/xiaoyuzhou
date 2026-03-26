from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Iterable

from .models import EpisodeCandidate, PodcastDefinition
from .utils import utc_now_iso

STATUS_DISCOVERED = "DISCOVERED"
STATUS_DOWNLOADED = "DOWNLOADED"
STATUS_TRANSCRIBED = "TRANSCRIBED"
STATUS_CLEANED = "CLEANED"
STATUS_INDEXED = "INDEXED"
STATUS_FAILED_RETRYABLE = "FAILED_RETRYABLE"
STATUS_FAILED_FINAL = "FAILED_FINAL"


class PipelineDB:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row

    def close(self) -> None:
        self.conn.close()

    def init_schema(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS podcasts (
                podcast_id TEXT PRIMARY KEY,
                display_name TEXT NOT NULL,
                source_url TEXT NOT NULL,
                rss_url TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS episodes (
                episode_id TEXT PRIMARY KEY,
                podcast_id TEXT NOT NULL,
                guid TEXT NOT NULL,
                title TEXT NOT NULL,
                source_url TEXT,
                audio_url TEXT NOT NULL,
                published_at TEXT,
                summary TEXT,
                raw_feed_json TEXT,
                status TEXT NOT NULL,
                last_stage TEXT,
                last_error TEXT,
                audio_path TEXT,
                transcript_path TEXT,
                cleaned_jsonl_path TEXT,
                summary_md_path TEXT,
                indexed_at TEXT,
                content_hash TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(podcast_id, guid),
                FOREIGN KEY (podcast_id) REFERENCES podcasts(podcast_id)
            );

            CREATE TABLE IF NOT EXISTS processing_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                episode_id TEXT NOT NULL,
                stage TEXT NOT NULL,
                status TEXT NOT NULL,
                detail TEXT,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                FOREIGN KEY (episode_id) REFERENCES episodes(episode_id)
            );

            CREATE VIRTUAL TABLE IF NOT EXISTS search_chunks USING fts5(
                chunk_id UNINDEXED,
                episode_id UNINDEXED,
                podcast_id UNINDEXED,
                episode_title UNINDEXED,
                source_url UNINDEXED,
                start_ms UNINDEXED,
                end_ms UNINDEXED,
                keywords UNINDEXED,
                summary UNINDEXED,
                text
            );
            """
        )
        self.conn.commit()

    def upsert_podcast(self, podcast: PodcastDefinition, rss_url: str) -> None:
        now = utc_now_iso()
        self.conn.execute(
            """
            INSERT INTO podcasts (podcast_id, display_name, source_url, rss_url, enabled, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(podcast_id) DO UPDATE SET
                display_name = excluded.display_name,
                source_url = excluded.source_url,
                rss_url = excluded.rss_url,
                enabled = excluded.enabled,
                updated_at = excluded.updated_at
            """,
            (
                podcast.podcast_id,
                podcast.display_name,
                podcast.source_url,
                rss_url,
                1 if podcast.enabled else 0,
                now,
                now,
            ),
        )
        self.conn.commit()

    def upsert_episode(self, episode: EpisodeCandidate) -> sqlite3.Row:
        existing = self.conn.execute(
            "SELECT * FROM episodes WHERE episode_id = ?",
            (episode.episode_id,),
        ).fetchone()
        now = utc_now_iso()
        if existing:
            self.conn.execute(
                """
                UPDATE episodes
                SET title = ?, source_url = ?, audio_url = ?, published_at = ?, summary = ?, raw_feed_json = ?, updated_at = ?
                WHERE episode_id = ?
                """,
                (
                    episode.title,
                    episode.source_url,
                    episode.audio_url,
                    episode.published_at,
                    episode.summary,
                    episode.raw_feed_json,
                    now,
                    episode.episode_id,
                ),
            )
        else:
            self.conn.execute(
                """
                INSERT INTO episodes (
                    episode_id, podcast_id, guid, title, source_url, audio_url, published_at, summary,
                    raw_feed_json, status, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    episode.episode_id,
                    episode.podcast_id,
                    episode.guid,
                    episode.title,
                    episode.source_url,
                    episode.audio_url,
                    episode.published_at,
                    episode.summary,
                    episode.raw_feed_json,
                    STATUS_DISCOVERED,
                    now,
                    now,
                ),
            )
        self.conn.commit()
        return self.get_episode(episode.episode_id)

    def get_episode(self, episode_id: str) -> sqlite3.Row:
        row = self.conn.execute(
            "SELECT * FROM episodes WHERE episode_id = ?",
            (episode_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"Episode {episode_id} not found")
        return row

    def get_episodes_by_status(self, statuses: Iterable[str]) -> list[sqlite3.Row]:
        statuses = list(statuses)
        placeholders = ", ".join("?" for _ in statuses)
        return list(
            self.conn.execute(
                f"SELECT * FROM episodes WHERE status IN ({placeholders}) ORDER BY published_at, created_at",
                tuple(statuses),
            ).fetchall()
        )

    def get_failed_retryable(self) -> list[sqlite3.Row]:
        return self.get_episodes_by_status([STATUS_FAILED_RETRYABLE])

    def update_episode_fields(self, episode_id: str, **fields: object) -> None:
        if not fields:
            return
        columns = ", ".join(f"{key} = ?" for key in fields)
        values = list(fields.values()) + [utc_now_iso(), episode_id]
        self.conn.execute(
            f"UPDATE episodes SET {columns}, updated_at = ? WHERE episode_id = ?",
            values,
        )
        self.conn.commit()

    def mark_stage_started(self, episode_id: str, stage: str, detail: dict | None = None) -> int:
        now = utc_now_iso()
        cursor = self.conn.execute(
            """
            INSERT INTO processing_runs (episode_id, stage, status, detail, started_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (episode_id, stage, "STARTED", json.dumps(detail or {}, ensure_ascii=False), now),
        )
        self.conn.commit()
        return int(cursor.lastrowid)

    def mark_stage_finished(
        self,
        run_id: int,
        episode_id: str,
        stage: str,
        status: str,
        *,
        last_error: str | None = None,
        detail: dict | None = None,
        extra_fields: dict | None = None,
    ) -> None:
        now = utc_now_iso()
        self.conn.execute(
            """
            UPDATE processing_runs
            SET status = ?, detail = ?, finished_at = ?
            WHERE id = ?
            """,
            (status, json.dumps(detail or {}, ensure_ascii=False), now, run_id),
        )
        fields = {"status": status, "last_stage": stage, "last_error": last_error or ""}
        if extra_fields:
            fields.update(extra_fields)
        self.update_episode_fields(episode_id, **fields)
        self.conn.commit()

    def reset_failed_episode(self, episode_id: str, target_status: str) -> None:
        self.update_episode_fields(episode_id, status=target_status, last_error="")

    def podcast_counts(self) -> dict[str, int]:
        rows = self.conn.execute(
            "SELECT status, COUNT(*) AS count FROM episodes GROUP BY status"
        ).fetchall()
        return {row["status"]: int(row["count"]) for row in rows}
