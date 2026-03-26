from podcast_pipeline.knowledge_agent import fallback_answer


def test_fallback_answer_lists_sources() -> None:
    payload = {
        "results": [
            {"episode_id": "ep-1", "episode_title": "EP001", "summary": "第一条摘要"},
            {"episode_id": "ep-2", "episode_title": "EP002", "text": "第二条正文"},
        ]
    }
    answer = fallback_answer(payload)
    assert "EP001" in answer
    assert "第一条摘要" in answer
    assert "EP002" in answer
