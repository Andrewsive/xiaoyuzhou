from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, render_template_string, request

from .config import AppConfig, load_config
from .pipeline import PipelineRunner


@dataclass(slots=True)
class AgentSearchHit:
    score: float
    text: str
    episode_title: str
    source_url: str
    start_ms: int | None
    end_ms: int | None
    summary: str
    podcast_id: str
    episode_id: str


def normalize_hits(raw_hits: list[dict[str, Any]]) -> list[AgentSearchHit]:
    hits: list[AgentSearchHit] = []
    for item in raw_hits:
        metadata = item.get("metadata", {})
        start_ms = metadata.get("start_ms")
        end_ms = metadata.get("end_ms")
        hits.append(
            AgentSearchHit(
                score=float(item.get("score", 0.0)),
                text=str(item.get("text", "")).strip(),
                episode_title=str(metadata.get("episode_title", "")),
                source_url=str(metadata.get("source_url", "")),
                start_ms=int(start_ms) if start_ms not in (None, "") else None,
                end_ms=int(end_ms) if end_ms not in (None, "") else None,
                summary=str(metadata.get("summary", "")),
                podcast_id=str(metadata.get("podcast_id", "")),
                episode_id=str(metadata.get("episode_id", "")),
            )
        )
    return hits


def format_agent_context(hits: list[AgentSearchHit]) -> str:
    parts: list[str] = []
    for index, hit in enumerate(hits, start=1):
        time_window = ""
        if hit.start_ms is not None and hit.end_ms is not None:
            time_window = f" [{hit.start_ms}-{hit.end_ms}ms]"
        parts.append(f"[{index}] {hit.episode_title}{time_window}\n{hit.text}")
    return "\n\n".join(parts).strip()


def serialize_hits(hits: list[AgentSearchHit]) -> list[dict[str, Any]]:
    return [
        {
            "score": hit.score,
            "text": hit.text,
            "episode_title": hit.episode_title,
            "source_url": hit.source_url,
            "start_ms": hit.start_ms,
            "end_ms": hit.end_ms,
            "summary": hit.summary,
            "podcast_id": hit.podcast_id,
            "episode_id": hit.episode_id,
        }
        for hit in hits
    ]


def build_agent_payload(raw_hits: list[dict[str, Any]], *, query: str) -> dict[str, Any]:
    hits = normalize_hits(raw_hits)
    return {
        "query": query,
        "total_hits": len(hits),
        "context": format_agent_context(hits),
        "results": serialize_hits(hits),
    }


def create_agent_app(config_path: Path) -> Flask:
    app = Flask(__name__)
    app.json.ensure_ascii = False
    config = load_config(config_path)

    @app.get("/")
    def home() -> Any:
        return render_template_string(
            """
            <!doctype html>
            <html lang="zh-CN">
              <head>
                <meta charset="utf-8">
                <title>Podcast Knowledge Base Demo</title>
                <style>
                  body { font-family: "Microsoft YaHei", sans-serif; margin: 40px; line-height: 1.6; color: #1f2937; }
                  h1 { margin-bottom: 8px; }
                  code, pre { background: #f3f4f6; padding: 2px 6px; border-radius: 6px; }
                  pre { padding: 12px; overflow: auto; }
                  a { color: #2563eb; text-decoration: none; }
                  .card { border: 1px solid #e5e7eb; border-radius: 12px; padding: 16px; margin-top: 16px; }
                </style>
              </head>
              <body>
                <h1>播客知识库本地服务</h1>
                <p>服务已经启动成功。这个页面是给人看的演示入口，真正给程序调用的是下面这些接口。</p>

                <div class="card">
                  <h2>可直接打开</h2>
                  <p><a href="/health" target="_blank">/health</a></p>
                  <p><a href="/v1/search?q=年轻化&top_k=5" target="_blank">/v1/search?q=年轻化&top_k=5</a></p>
                  <p><a href="/v1/search?q=这几集播客讲了哪些内容&top_k=5" target="_blank">/v1/search?q=这几集播客讲了哪些内容&top_k=5</a></p>
                </div>

                <div class="card">
                  <h2>给 Agent 调用</h2>
                  <pre>POST /v1/retrieve
Content-Type: application/json

{
  "query": "这几集播客讲了哪些内容",
  "top_k": 5
}</pre>
                </div>
              </body>
            </html>
            """
        )

    @app.get("/health")
    def health() -> Any:
        runner = PipelineRunner(config)
        try:
            stats = runner.stats()
        finally:
            runner.close()
        return jsonify({"ok": True, "counts": stats["counts"], "vector_path": stats["vector_path"]})

    @app.get("/v1/search")
    def search() -> Any:
        query = request.args.get("q", "").strip()
        top_k = int(request.args.get("top_k", "5"))
        if not query:
            return jsonify({"error": "Missing query parameter q"}), 400
        runner = PipelineRunner(config)
        try:
            raw_hits = runner.search(query=query, top_k=top_k)
        finally:
            runner.close()
        return jsonify(build_agent_payload(raw_hits, query=query))

    @app.post("/v1/retrieve")
    def retrieve() -> Any:
        payload = request.get_json(silent=True) or {}
        query = str(payload.get("query", "")).strip()
        top_k = int(payload.get("top_k", 5))
        if not query:
            return jsonify({"error": "Missing JSON field query"}), 400
        runner = PipelineRunner(config)
        try:
            raw_hits = runner.search(query=query, top_k=top_k)
        finally:
            runner.close()
        return jsonify(build_agent_payload(raw_hits, query=query))

    return app
