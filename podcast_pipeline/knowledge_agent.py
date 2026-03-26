from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from .agent_service import build_agent_payload
from .config import load_config
from .http_clients import OpenAICompatibleClient
from .pipeline import PipelineRunner


SYSTEM_PROMPT = """You answer questions using podcast knowledge base retrieval results.
Rules:
- Use the provided context as your primary evidence.
- If the context is insufficient, say so clearly.
- Keep the answer concise and cite episode titles when possible.
- Answer in Simplified Chinese when the question is Chinese.
"""


def load_llm_env(config_path: Path) -> tuple[str, str, str] | None:
    load_dotenv(config_path.parent / ".env")
    api_key = os.getenv("LLM_API_KEY", "").strip()
    base_url = os.getenv("LLM_BASE_URL", "").strip()
    model = os.getenv("LLM_MODEL", "").strip()
    if api_key and base_url and model:
        return api_key, base_url, model
    return None


def _truncate(text: str, limit: int = 160) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[:limit].rstrip()}..."


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
        raw_hits = runner.search(query=question, top_k=top_k)
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
                f"知识库上下文：\n{payload.get('context', '')}\n\n"
                "请基于这些检索结果直接回答。如果证据不足，请明确说明。"
            ),
        },
    ]
    payload["answer"] = client.chat(model=model, messages=messages, temperature=0.2)
    payload["answer_mode"] = "llm"
    return payload


def print_agent_answer(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)
