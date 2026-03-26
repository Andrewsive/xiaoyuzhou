from pathlib import Path

from podcast_pipeline.cleaner import group_segments
from podcast_pipeline.config import AppConfig, CleanerConfig, DashScopeAsrConfig, DatabaseConfig, EmbeddingConfig, RssHubConfig, StorageConfig
from podcast_pipeline.db import PipelineDB
from podcast_pipeline.models import TranscriptSegment
from podcast_pipeline.indexer import VectorIndexer
from podcast_pipeline.utils import extract_episode_id, extract_podcast_id, guess_extension_from_url
from podcast_pipeline.xiaoyuzhou_web import XiaoyuzhouWebSource


def test_extract_podcast_id() -> None:
    url = "https://www.xiaoyuzhoufm.com/podcast/5e280faf418a84a0461fa1eb"
    assert extract_podcast_id(url) == "5e280faf418a84a0461fa1eb"


def test_guess_extension_from_url() -> None:
    url = "https://cdn.example.com/audio/demo.m4a?token=abc"
    assert guess_extension_from_url(url) == ".m4a"


def test_extract_episode_id() -> None:
    url = "https://www.xiaoyuzhoufm.com/episode/67c31846bf52a16cd1d8b39b"
    assert extract_episode_id(url) == "67c31846bf52a16cd1d8b39b"


def test_group_segments_respects_limit() -> None:
    segments = [
        TranscriptSegment(segment_id="1", text="hello", start_ms=0, end_ms=1000, speaker="a"),
        TranscriptSegment(segment_id="2", text="world", start_ms=1000, end_ms=2000, speaker="a"),
        TranscriptSegment(segment_id="3", text="python", start_ms=2000, end_ms=3000, speaker="b"),
    ]
    groups = group_segments(segments, max_chars=8)
    assert len(groups) == 3
    assert groups[0][0].start_ms == 0
    assert groups[-1][0].speaker == "b"


def test_resolve_source_from_episode_url(monkeypatch) -> None:
    source = XiaoyuzhouWebSource()

    def fake_fetch(url: str) -> dict:
        assert url.endswith("/episode/67c31846bf52a16cd1d8b39b")
        return {
            "props": {
                "pageProps": {
                    "episode": {
                        "pid": "61e7b5314675a08411f51319",
                        "podcast": {
                            "title": "Talk三联",
                            "author": "Talk三联",
                            "description": "sample",
                        },
                    }
                }
            }
        }

    monkeypatch.setattr(source, "_fetch_next_data", fake_fetch)
    resolved = source.resolve_url("https://www.xiaoyuzhoufm.com/episode/67c31846bf52a16cd1d8b39b")
    assert resolved.podcast_id == "61e7b5314675a08411f51319"
    assert resolved.source_url.endswith("/podcast/61e7b5314675a08411f51319")


def test_sqlite_fts_like_fallback(tmp_path: Path) -> None:
    db_path = tmp_path / "pipeline.db"
    config = AppConfig(
        database=DatabaseConfig(path=str(db_path)),
        rsshub=RssHubConfig(),
        asr=DashScopeAsrConfig(),
        cleaner=CleanerConfig(),
        embedding=EmbeddingConfig(provider="sqlite_fts"),
        storage=StorageConfig(base_dir="data"),
        podcasts=[],
        workspace_root=tmp_path,
    )
    config.ensure_directories()
    db = PipelineDB(config.database_path)
    db.init_schema()
    db.close()

    jsonl_path = tmp_path / "episode.jsonl"
    jsonl_path.write_text(
        '{"chunk_id":"c1","text":"我们讨论品牌年轻化的问题","start_ms":0,"end_ms":1000,"speaker":"s","keywords":[],"summary":"品牌年轻化"}\n',
        encoding="utf-8",
    )
    indexer = VectorIndexer(config)
    indexer.index_episode(
        episode={
            "episode_id": "ep1",
            "podcast_id": "pod1",
            "title": "Episode 1",
            "source_url": "https://example.com/ep1",
            "audio_url": "https://example.com/ep1.mp3",
            "published_at": "2026-01-01T00:00:00Z",
        },
        cleaned_jsonl_path=jsonl_path,
    )
    results = indexer.search(query="年轻化", top_k=5)
    assert results
    assert "年轻化" in results[0]["text"]
