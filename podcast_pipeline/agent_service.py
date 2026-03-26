from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, request

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
    config = load_config(config_path)

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
