"""Subagent 2: Retrieval. Hybrid search (vectors + BM25 keywords) over only the routed collections,
returning numbered evidence."""

from __future__ import annotations

from collections import Counter

from agents.state import Evidence, GraphState
from rag.hybrid import HybridSearcher
from rag.llm import LLMClient
from rag.vector_store import VectorStore

K_PER_SOURCE = 4
MIN_SCORE = 0.30  # cosine similarity; vector-only matches below this are treated as unrelated
MAX_EVIDENCE = 8


class RetrievalAgent:
    name = "retrieval"

    def __init__(self, llm: LLMClient, store: VectorStore, searcher: HybridSearcher | None = None):
        self.llm = llm
        self.searcher = searcher or HybridSearcher(store)

    def __call__(self, state: GraphState) -> dict:
        sources = state["search_sources"]
        question = state["question"]
        emb = self.llm.embed([question])
        vector = emb.vectors[0]

        # Keep evidence from earlier passes; add new hits without duplicates.
        seen = {e["metadata"].get("chunk_id") for e in state.get("evidence", [])}
        hits = [
            h
            for src in sources
            for h in self.searcher.search(src, question, vector, K_PER_SOURCE, min_vector_score=MIN_SCORE)
            if h.id not in seen
        ]
        hits.sort(key=lambda h: h.score, reverse=True)

        evidence: list[Evidence] = list(state.get("evidence", []))
        added = hits[: max(0, MAX_EVIDENCE - len(evidence))]
        for h in added:
            evidence.append(
                Evidence(
                    id=f"E{len(evidence) + 1}",
                    text=h.text,
                    score=h.score,
                    metadata={**h.metadata, "chunk_id": h.id, "matched_by": h.matched_by},
                )
            )
        by = Counter(h.matched_by for h in added)
        mix = ", ".join(f"{n} {k}" for k, n in sorted(by.items())) or "none"
        searched = sorted(set(state.get("searched_sources", [])) | set(sources))
        return {
            "evidence": evidence,
            "searched_sources": searched,
            "retrieval_done": True,
            "trace": [f"retrieval: {self.searcher.mode} search of {sources}, kept {len(evidence)} passages "
                      f"(matched by {mix})"],
            "tokens": emb.total_tokens,
            "cost_usd": emb.cost_usd,
        }
