from podcast_pipeline.knowledge_agent import _resolve_llm_settings, fallback_answer


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
