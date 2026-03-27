from podcast_pipeline.knowledge_agent import (
    _dedupe_hits_by_episode,
    _is_overview_question,
    _resolve_llm_settings,
    fallback_answer,
)


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


def test_resolve_llm_settings_reuses_embedding_provider() -> None:
    settings = _resolve_llm_settings(
        {
            "LLM_API_KEY": "",
            "LLM_BASE_URL": "",
            "LLM_MODEL": "",
            "EMBEDDING_API_KEY": "embedding-key",
            "EMBEDDING_BASE_URL": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        }
    )
    assert settings == (
        "embedding-key",
        "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "qwen-plus",
    )


def test_is_overview_question_detects_episode_summary_intent() -> None:
    assert _is_overview_question("这5集播客分别讲了什么内容")
    assert _is_overview_question("请给我一个最近几集的总览")
    assert not _is_overview_question("哪一集谈到了年轻化")


def test_dedupe_hits_by_episode_keeps_one_hit_per_episode() -> None:
    raw_hits = [
        {"text": "a", "metadata": {"episode_id": "ep-1"}},
        {"text": "b", "metadata": {"episode_id": "ep-1"}},
        {"text": "c", "metadata": {"episode_id": "ep-2"}},
    ]
    deduped = _dedupe_hits_by_episode(raw_hits, limit=5)
    assert len(deduped) == 2
    assert deduped[0]["metadata"]["episode_id"] == "ep-1"
    assert deduped[1]["metadata"]["episode_id"] == "ep-2"
