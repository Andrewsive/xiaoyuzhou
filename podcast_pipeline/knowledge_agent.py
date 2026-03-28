from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from .agent_service import build_agent_payload
from .config import load_config
from .db import STATUS_INDEXED
from .http_clients import OpenAICompatibleClient
from .pipeline import PipelineRunner


SYSTEM_PROMPT = """You answer questions using podcast knowledge base retrieval results.
Rules:
- Use the provided context as your primary evidence.
- If the context is insufficient, say so clearly.
- Keep the answer concise and cite episode titles when possible.
- Answer in Simplified Chinese when the question is Chinese.
- Treat structured metadata such as episode titles as higher-priority evidence than inferred guesses from transcript snippets.
- Do not "correct" person names, titles, or works unless the provided evidence explicitly proves they are wrong.
- If the title and snippet conflict, report the conflict instead of choosing one side as a factual correction.
"""


def _default_model_for_base_url(base_url: str) -> str | None:
    normalized = base_url.strip().lower()
    if "dashscope.aliyuncs.com/compatible-mode/v1" in normalized:
        return "qwen-plus"
    if "api.openai.com/v1" in normalized:
        return "gpt-4o-mini"
    return None


def _resolve_llm_settings(env: dict[str, str]) -> tuple[str, str, str] | None:
    api_key = env.get("LLM_API_KEY", "").strip()
    base_url = env.get("LLM_BASE_URL", "").strip()
    model = env.get("LLM_MODEL", "").strip()
    if api_key and base_url and model:
        return api_key, base_url, model

    # Reuse the embedding provider when the key is shared across compatible APIs.
    embedding_api_key = env.get("EMBEDDING_API_KEY", "").strip()
    embedding_base_url = env.get("EMBEDDING_BASE_URL", "").strip()
    if not embedding_api_key:
        return None

    api_key = api_key or embedding_api_key
    base_url = base_url or embedding_base_url
    model = model or _default_model_for_base_url(base_url or embedding_base_url) or ""
    if api_key and base_url and model:
        return api_key, base_url, model
    return None


def load_llm_env(config_path: Path) -> tuple[str, str, str] | None:
    load_dotenv(config_path.parent / ".env")
    env = {
        "LLM_API_KEY": os.getenv("LLM_API_KEY", ""),
        "LLM_BASE_URL": os.getenv("LLM_BASE_URL", ""),
        "LLM_MODEL": os.getenv("LLM_MODEL", ""),
        "EMBEDDING_API_KEY": os.getenv("EMBEDDING_API_KEY", ""),
        "EMBEDDING_BASE_URL": os.getenv("EMBEDDING_BASE_URL", ""),
    }
    return _resolve_llm_settings(env)


def _truncate(text: str, limit: int = 160) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[:limit].rstrip()}..."


def _format_answer_evidence(payload: dict[str, Any]) -> str:
    lines: list[str] = []
    for index, item in enumerate(payload.get("results", []), start=1):
        title = str(item.get("episode_title", "")).strip()
        summary = str(item.get("summary", "")).strip()
        snippet = str(item.get("text", "")).strip()
        source_url = str(item.get("source_url", "")).strip()
        evidence = summary or _truncate(snippet, limit=300)
        lines.append(f"[{index}] 标题: {title}")
        if evidence:
            lines.append(f"摘要: {evidence}")
        if source_url:
            lines.append(f"来源: {source_url}")
        lines.append("")
    return "\n".join(lines).strip()


def _is_overview_question(question: str) -> bool:
    normalized = re.sub(r"\s+", "", question.lower())
    overview_markers = (
        "这几集",
        "这5集",
        "这五集",
        "最近几集",
        "所有已入库",
        "全部已入库",
        "逐集",
        "分别讲了什么",
        "分别说了什么",
        "总览",
        "概览",
    )
    return any(marker in normalized for marker in overview_markers)


def _dedupe_hits_by_episode(raw_hits: list[dict[str, Any]], *, limit: int) -> list[dict[str, Any]]:
    unique_hits: list[dict[str, Any]] = []
    seen_episode_ids: set[str] = set()
    for item in raw_hits:
        episode_id = str(item.get("metadata", {}).get("episode_id", "")).strip()
        if episode_id and episode_id in seen_episode_ids:
            continue
        if episode_id:
            seen_episode_ids.add(episode_id)
        unique_hits.append(item)
        if len(unique_hits) >= limit:
            break
    return unique_hits


def fallback_answer(payload: dict[str, Any]) -> str:
    results = payload.get("results", [])
    if not results:
        return "知识库里没有检索到足够相关的内容，暂时无法可靠回答这个问题。"

    lines = ["根据当前知识库，相关内容主要来自这些节目：", ""]
    seen_episode_ids: set[str] = set()
    shown = 0
    for item in results:
        episode_id = str(item.get("episode_id", "")).strip()
        if episode_id and episode_id in seen_episode_ids:
            continue
        if episode_id:
            seen_episode_ids.add(episode_id)
        shown += 1
        snippet = str(item.get("summary") or item.get("text") or "").strip()
        lines.append(f"{shown}. {item.get('episode_title', '未命名节目')}")
        lines.append(f"   片段摘要：{_truncate(snippet)}")
        source_url = str(item.get("source_url", "")).strip()
        if source_url:
            lines.append(f"   来源：{source_url}")
        if shown >= 3:
            break
    return "\n".join(lines).strip()


def answer_with_knowledge_base(
    *,
    config_path: Path,
    question: str,
    top_k: int = 3,
) -> dict[str, Any]:
    config = load_config(config_path)
    runner = PipelineRunner(config)
    try:
        counts = runner.stats().get("counts", {})
        indexed_episode_count = int(counts.get(STATUS_INDEXED, 0))
        wants_overview = _is_overview_question(question)
        desired_episodes = max(top_k, indexed_episode_count) if wants_overview and indexed_episode_count else top_k
        candidate_hits = min(max(desired_episodes * 3, top_k), 30) if wants_overview else top_k
        raw_hits = runner.search(query=question, top_k=candidate_hits)
        if wants_overview:
            raw_hits = _dedupe_hits_by_episode(raw_hits, limit=desired_episodes)
    finally:
        runner.close()

    payload = build_agent_payload(raw_hits, query=question)
    llm_env = load_llm_env(config_path)
    if not llm_env:
        payload["answer"] = fallback_answer(payload)
        payload["answer_mode"] = "fallback"
        return payload

    api_key, base_url, model = llm_env
    client = OpenAICompatibleClient(api_key=api_key, base_url=base_url)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"用户问题：{question}\n\n"
                f"结构化检索结果：\n{_format_answer_evidence(payload)}\n\n"
                f"原始知识库上下文：\n{payload.get('context', '')}\n\n"
                "请基于这些检索结果直接回答。\n"
                "优先信任标题和摘要，不要擅自纠正人名、片名或节目标题。\n"
                "如果证据之间存在冲突，请明确写出“检索结果存在冲突”，不要自行裁定。"
            ),
        },
    ]
    payload["answer"] = client.chat(model=model, messages=messages, temperature=0.2)
    payload["answer_mode"] = "llm"
    return payload


def print_agent_answer(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)
