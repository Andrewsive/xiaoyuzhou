from __future__ import annotations

import json
import requests


BASE_URL = "http://127.0.0.1:8787"


def retrieve_context(query: str, top_k: int = 3) -> dict:
    try:
        response = requests.post(
            f"{BASE_URL}/v1/retrieve",
            json={"query": query, "top_k": top_k},
            timeout=30,
        )
    except requests.RequestException as exc:
        raise SystemExit(
            "Could not connect to the local agent service. "
            "Start it first with: "
            "C:\\Users\\yichen\\miniconda3\\python.exe -m podcast_pipeline serve-agent --host 127.0.0.1 --port 8787"
        ) from exc
    response.raise_for_status()
    return response.json()


def build_agent_messages(question: str, retrieved: dict) -> list[dict[str, str]]:
    context = retrieved.get("context", "").strip()
    return [
        {
            "role": "system",
            "content": (
                "你是一个播客知识库问答助手。"
                "优先依据提供的检索上下文回答；如果上下文不足，要明确说明不确定。"
            ),
        },
        {
            "role": "user",
            "content": (
                f"用户问题：{question}\n\n"
                f"检索到的知识库上下文：\n{context}\n\n"
                "请基于以上内容回答，并尽量引用对应节目内容。"
            ),
        },
    ]


def main() -> None:
    question = "Talk三联最近几期里，哪些内容谈到了年轻化？"
    retrieved = retrieve_context(question, top_k=3)
    messages = build_agent_messages(question, retrieved)

    print("=== Retrieved Payload ===")
    print(json.dumps(retrieved, ensure_ascii=False, indent=2))
    print("\n=== Example Messages For Your Agent ===")
    print(json.dumps(messages, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
