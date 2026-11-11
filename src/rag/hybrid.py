"""Hybrid retrieval: vector similarity (Chroma) + BM25 keywords, merged with Reciprocal Rank Fusion.

For each source, both retrievers return their top candidates. RRF scores each chunk by
sum(1 / (RRF_K + rank)) over the lists it appears in, so a chunk ranked well by both wins, and
a chunk found by only one can still make the cut. Scores are scaled to 0-1, where 1 means
ranked first by both retrievers.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal

from langsmith import traceable

from .keyword_index import BM25Index
from .vector_store import VectorStore

Mode = Literal["hybrid", "vector"]
RETRIEVAL_MODE: Mode = "vector" if os.getenv("RETRIEVAL_MODE", "hybrid").lower() == "vector" else "hybrid"

RRF_K = 60  # standard RRF constant; dampens the gap between rank 1 and rank 2
CANDIDATES = 10  # candidates taken from each retriever before fusion
_MAX_RRF = 2 / (RRF_K + 1)


@dataclass
class Hit:
    id: str
    text: str
    metadata: dict
    score: float  # fused, 0-1
    vector_score: float | None  # cosine similarity, if found by vector search
    keyword_score: float | None  # BM25, if found by keyword search

    @property
    def matched_by(self) -> str:
        if self.vector_score is not None and self.keyword_score is not None:
            return "both"
        return "vector" if self.vector_score is not None else "keyword"

    def as_dict(self) -> dict:
        return {"id": self.id, "text": self.text, "metadata": self.metadata, "score": self.score,
                "vector_score": self.vector_score, "keyword_score": self.keyword_score,
                "matched_by": self.matched_by}


def _trace_inputs(inputs: dict) -> dict:
    """LangSmith: show what was searched, not the 1,536-number vector or the searcher object."""
    return {k: inputs.get(k) for k in ("source", "question", "k", "min_vector_score")}


def _trace_outputs(outputs) -> dict:
    """LangSmith: show hits as documents (text, source, page, scores) in the retriever view."""
    hits = outputs.get("output", outputs) if isinstance(outputs, dict) else outputs
    return {"documents": [
        {"type": "Document", "page_content": h.text,
         "metadata": {**h.metadata, "chunk_id": h.id, "score": h.score, "matched_by": h.matched_by}}
        for h in hits
    ]}


class HybridSearcher:
    def __init__(self, store: VectorStore, mode: Mode = RETRIEVAL_MODE):
        self.store = store
        self.mode = mode
        self._indexes: dict[str, tuple[tuple, BM25Index, dict]] = {}

    def _keyword_index(self, source: str) -> tuple[BM25Index, dict]:
        """BM25 index for a source, rebuilt automatically when the collection is re-ingested."""
        col = self.store.collection(source)
        version = (str(col.id), col.count())
        cached = self._indexes.get(source)
        if cached and cached[0] == version:
            return cached[1], cached[2]
        data = col.get(include=["documents", "metadatas"])
        index = BM25Index(data["ids"], data["documents"])
        docs = {i: (d, m) for i, d, m in zip(data["ids"], data["documents"], data["metadatas"])}
        self._indexes[source] = (version, index, docs)
        return index, docs

    @traceable(run_type="retriever", name="hybrid_search", process_inputs=_trace_inputs, process_outputs=_trace_outputs)
    def search(self, source: str, question: str, vector: list[float], k: int, min_vector_score: float = 0.0) -> list[Hit]:
        vec_hits = [h for h in self.store.query(source, vector, CANDIDATES) if h["score"] >= min_vector_score]
        if self.mode == "vector":
            return [Hit(h["id"], h["text"], h["metadata"], round(h["score"], 4), h["score"], None) for h in vec_hits[:k]]

        index, docs = self._keyword_index(source)
        kw_hits = index.search(question, CANDIDATES)

        fused: dict[str, dict] = {}
        for rank, h in enumerate(vec_hits, start=1):
            fused[h["id"]] = {"rrf": 1 / (RRF_K + rank), "vec": h["score"], "kw": None,
                              "text": h["text"], "meta": h["metadata"]}
        for rank, (cid, s) in enumerate(kw_hits, start=1):
            entry = fused.get(cid)
            if entry is None:
                text, meta = docs[cid]
                entry = fused[cid] = {"rrf": 0.0, "vec": None, "kw": None, "text": text, "meta": meta}
            entry["rrf"] += 1 / (RRF_K + rank)
            entry["kw"] = s

        ranked = sorted(fused.items(), key=lambda kv: kv[1]["rrf"], reverse=True)[:k]
        return [
            Hit(cid, e["text"], e["meta"], round(e["rrf"] / _MAX_RRF, 4),
                None if e["vec"] is None else round(e["vec"], 4),
                None if e["kw"] is None else round(e["kw"], 3))
            for cid, e in ranked
        ]
