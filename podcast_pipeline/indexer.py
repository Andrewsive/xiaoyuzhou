from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any

from .config import AppConfig
from .http_clients import OpenAICompatibleClient
from .utils import getenv_required, sanitize_collection_value


def load_clean_segments(jsonl_path: Path) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for line in jsonl_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            items.append(json.loads(line))
    return items


class VectorIndexer:
    def __init__(self, config: AppConfig):
        self.config = config
        self.mode = self._resolve_mode()
        self.client = None
        self.embedding_model = None
        self.persist_path = str(config.vector_path)
        self.collection_name = config.embedding.collection_name
        self.chromadb = None
        if self.mode == "chroma":
            import chromadb

            self.chromadb = chromadb
            self.client = OpenAICompatibleClient(
                api_key=getenv_required(config.embedding.api_key_env),
                base_url=config.embedding_base_url(),
            )
            self.embedding_model = config.embedding_model()

    def _resolve_mode(self) -> str:
        provider = self.config.embedding.provider.lower()
        if provider == "sqlite_fts":
            return "sqlite_fts"
        if provider == "openai":
            return "chroma"
        has_embedding_key = bool(os.getenv(self.config.embedding.api_key_env, "").strip())
        if not has_embedding_key:
            return "sqlite_fts"
        try:
            import chromadb  # noqa: F401
        except ImportError:
            return "sqlite_fts"
        return "chroma"

    def index_episode(self, *, episode: dict, cleaned_jsonl_path: Path) -> int:
        segments = load_clean_segments(cleaned_jsonl_path)
        if not segments:
            return 0

        if self.mode == "sqlite_fts":
            return self._index_with_fts(episode=episode, segments=segments)

        client = self.chromadb.PersistentClient(path=self.persist_path)
        collection = client.get_or_create_collection(name=self.collection_name, metadata={"hnsw:space": "cosine"})
        collection.delete(where={"episode_id": episode["episode_id"]})

        documents = [item["text"] for item in segments]
        embeddings = self.client.embeddings(model=self.embedding_model, texts=documents)
        ids = [item["chunk_id"] for item in segments]
        metadatas = []
        for item in segments:
            metadatas.append(
                {
                    "podcast_id": sanitize_collection_value(episode["podcast_id"]),
                    "episode_id": sanitize_collection_value(episode["episode_id"]),
                    "episode_title": sanitize_collection_value(episode["title"]),
                    "published_at": sanitize_collection_value(episode["published_at"]),
                    "source_url": sanitize_collection_value(episode["source_url"]),
                    "audio_url": sanitize_collection_value(episode["audio_url"]),
                    "start_ms": int(item["start_ms"]),
                    "end_ms": int(item["end_ms"]),
                    "speaker": sanitize_collection_value(item.get("speaker", "")),
                    "keywords": sanitize_collection_value(item.get("keywords", [])),
                    "summary": sanitize_collection_value(item.get("summary", "")),
                }
            )

        collection.upsert(ids=ids, documents=documents, metadatas=metadatas, embeddings=embeddings)
        return len(ids)

    def search(self, *, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        if self.mode == "sqlite_fts":
            return self._search_with_fts(query=query, top_k=top_k)

        client = self.chromadb.PersistentClient(path=self.persist_path)
        collection = client.get_or_create_collection(name=self.collection_name, metadata={"hnsw:space": "cosine"})
        query_embedding = self.client.embeddings(model=self.embedding_model, texts=[query])[0]
        results = collection.query(query_embeddings=[query_embedding], n_results=top_k)

        documents = results.get("documents", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]
        items: list[dict[str, Any]] = []
        for document, metadata, distance in zip(documents, metadatas, distances):
            items.append(
                {
                    "text": document,
                    "score": 1 - float(distance),
                    "metadata": metadata,
                }
            )
        return items

    def _index_with_fts(self, *, episode: dict, segments: list[dict[str, Any]]) -> int:
        conn = sqlite3.connect(self.config.database_path)
        conn.execute("DELETE FROM search_chunks WHERE episode_id = ?", (episode["episode_id"],))
        for item in segments:
            conn.execute(
                """
                INSERT INTO search_chunks (
                    chunk_id, episode_id, podcast_id, episode_title, source_url,
                    start_ms, end_ms, keywords, summary, text
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item["chunk_id"],
                    episode["episode_id"],
                    episode["podcast_id"],
                    episode["title"],
                    episode["source_url"],
                    str(item["start_ms"]),
                    str(item["end_ms"]),
                    sanitize_collection_value(item.get("keywords", [])),
                    sanitize_collection_value(item.get("summary", "")),
                    item["text"],
                ),
            )
        conn.commit()
        conn.close()
        return len(segments)

    def _search_with_fts(self, *, query: str, top_k: int) -> list[dict[str, Any]]:
        conn = sqlite3.connect(self.config.database_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT chunk_id, episode_id, podcast_id, episode_title, source_url, start_ms, end_ms, keywords, summary, text,
                   bm25(search_chunks) AS score
            FROM search_chunks
            WHERE search_chunks MATCH ?
            ORDER BY score
            LIMIT ?
            """,
            (query, top_k),
        ).fetchall()
        if not rows:
            like_query = f"%{query}%"
            rows = conn.execute(
                """
                SELECT chunk_id, episode_id, podcast_id, episode_title, source_url, start_ms, end_ms, keywords, summary, text,
                       0.0 AS score
                FROM search_chunks
                WHERE text LIKE ? OR summary LIKE ? OR keywords LIKE ?
                LIMIT ?
                """,
                (like_query, like_query, like_query, top_k),
            ).fetchall()
        conn.close()
        return [
            {
                "text": row["text"],
                "score": float(-row["score"]),
                "metadata": {
                    "chunk_id": row["chunk_id"],
                    "episode_id": row["episode_id"],
                    "podcast_id": row["podcast_id"],
                    "episode_title": row["episode_title"],
                    "source_url": row["source_url"],
                    "start_ms": row["start_ms"],
                    "end_ms": row["end_ms"],
                    "keywords": row["keywords"],
                    "summary": row["summary"],
                },
            }
            for row in rows
        ]
