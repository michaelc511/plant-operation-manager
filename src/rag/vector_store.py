"""Local Chroma vector store with one collection per knowledge source."""

from __future__ import annotations

from pathlib import Path

import chromadb

from .config import CHROMA_DIR
from .pdf_loader import Chunk


class VectorStore:
    def __init__(self, path: Path | str = CHROMA_DIR, client=None):
        if client is None:
            Path(path).mkdir(parents=True, exist_ok=True)
            client = chromadb.PersistentClient(path=str(path))
        self.client = client

    def collection(self, source: str):
        # We always pass our own OpenAI embeddings, so no Chroma embedding function.
        return self.client.get_or_create_collection(
            name=source, metadata={"hnsw:space": "cosine"}, embedding_function=None
        )

    def reset(self, source: str) -> None:
        try:
            self.client.delete_collection(source)
        except Exception:  # collection did not exist yet
            pass

    def add(self, source: str, chunks: list[Chunk], vectors: list[list[float]]) -> None:
        if len(chunks) != len(vectors):
            raise ValueError("chunks and vectors must have the same length")
        self.collection(source).add(
            ids=[f"{source}-{c.chunk_index:04d}" for c in chunks],
            documents=[c.text for c in chunks],
            metadatas=[c.to_metadata() for c in chunks],
            embeddings=vectors,
        )

    def count(self, source: str) -> int:
        return self.collection(source).count()

    def query(self, source: str, vector: list[float], k: int = 4) -> list[dict]:
        res = self.collection(source).query(query_embeddings=[vector], n_results=k)
        return [
            {"id": i, "text": d, "metadata": m, "score": 1 - dist}
            for i, d, m, dist in zip(res["ids"][0], res["documents"][0], res["metadatas"][0], res["distances"][0])
        ]
