from __future__ import annotations

import json
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
        try:
            import chromadb
        except ImportError as exc:
            raise RuntimeError(
                "chromadb is not installed. Run `python -m pip install chromadb` before indexing."
            ) from exc

        self.chromadb = chromadb
        self.config = config
        self.client = OpenAICompatibleClient(
            api_key=getenv_required(config.embedding.api_key_env),
            base_url=config.embedding_base_url(),
        )
        self.embedding_model = config.embedding_model()
        self.persist_path = str(config.vector_path)
        self.collection_name = config.embedding.collection_name

    def index_episode(self, *, episode: dict, cleaned_jsonl_path: Path) -> int:
        segments = load_clean_segments(cleaned_jsonl_path)
        if not segments:
            return 0

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
