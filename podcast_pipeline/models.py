from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class PodcastDefinition:
    podcast_id: str
    display_name: str
    source_url: str
    rss_url: str | None = None
    enabled: bool = True


@dataclass(slots=True)
class EpisodeCandidate:
    episode_id: str
    podcast_id: str
    podcast_title: str
    guid: str
    title: str
    source_url: str
    audio_url: str
    published_at: str
    summary: str = ""
    raw_feed_json: str = ""


@dataclass(slots=True)
class TranscriptSegment:
    segment_id: str
    text: str
    start_ms: int
    end_ms: int
    speaker: str = "unknown"


@dataclass(slots=True)
class CleanSegment:
    chunk_id: str
    text: str
    start_ms: int
    end_ms: int
    speaker: str
    keywords: list[str] = field(default_factory=list)
    summary: str = ""


@dataclass(slots=True)
class EpisodeArtifacts:
    audio_path: Path | None = None
    transcript_path: Path | None = None
    cleaned_jsonl_path: Path | None = None
    summary_md_path: Path | None = None
