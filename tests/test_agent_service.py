from podcast_pipeline.agent_service import build_agent_payload, format_agent_context, normalize_hits


def test_build_agent_payload_formats_context() -> None:
    raw_hits = [
        {
            "score": 0.91,
            "text": "第一段内容",
            "metadata": {
                "episode_title": "EP001",
                "source_url": "https://example.com/ep1",
                "start_ms": 0,
                "end_ms": 1200,
                "summary": "摘要",
                "podcast_id": "pod1",
                "episode_id": "ep1",
            },
        },
        {
            "score": 0.82,
            "text": "第二段内容",
            "metadata": {
                "episode_title": "EP002",
                "source_url": "https://example.com/ep2",
                "start_ms": 1500,
                "end_ms": 2400,
                "summary": "",
                "podcast_id": "pod1",
                "episode_id": "ep2",
            },
        },
    ]
    payload = build_agent_payload(raw_hits, query="测试")
    assert payload["query"] == "测试"
    assert payload["total_hits"] == 2
    assert "[1] EP001 [0-1200ms]" in payload["context"]
    assert "第二段内容" in payload["context"]
    assert payload["results"][0]["episode_id"] == "ep1"


def test_normalize_hits_handles_missing_timestamps() -> None:
    hits = normalize_hits(
        [
            {
                "score": 0.3,
                "text": "内容",
                "metadata": {"episode_title": "EP", "source_url": "", "summary": ""},
            }
        ]
    )
    assert hits[0].start_ms is None
    assert hits[0].end_ms is None
    assert format_agent_context(hits).startswith("[1] EP")
