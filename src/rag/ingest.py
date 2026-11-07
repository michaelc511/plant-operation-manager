"""Load each source PDF, embed its chunks with OpenAI and (re)build its vector-store collection."""

from __future__ import annotations

from dataclasses import dataclass

from .config import SOURCES
from .hybrid import HybridSearcher
from .llm import LLMClient
from .pdf_loader import load_chunks
from .vector_store import VectorStore


@dataclass
class IngestReport:
    source: str
    chunks: int
    tokens: int
    cost_usd: float
    latency_s: float


def ingest(sources: list[str] | None = None, llm: LLMClient | None = None, store: VectorStore | None = None) -> list[IngestReport]:
    """Re-index the given sources (default: all). Each source is rebuilt independently (FR7)."""
    llm = llm or LLMClient()
    store = store or VectorStore()
    reports = []
    for key in sources or list(SOURCES):
        source = SOURCES[key]
        chunks = load_chunks(source)
        emb = llm.embed([c.text for c in chunks])
        store.reset(key)
        store.add(key, chunks, emb.vectors)
        reports.append(IngestReport(key, len(chunks), emb.total_tokens, emb.cost_usd, emb.latency_s))
    return reports


def search(question: str, sources: list[str] | None = None, k: int = 4, llm: LLMClient | None = None,
           store: VectorStore | None = None, searcher: HybridSearcher | None = None) -> list[dict]:
    """Return the top-k chunks from each requested source, best first (hybrid search by default)."""
    llm = llm or LLMClient()
    searcher = searcher or HybridSearcher(store or VectorStore())
    vector = llm.embed([question]).vectors[0]
    hits = [h.as_dict() for key in sources or list(SOURCES) for h in searcher.search(key, question, vector, k)]
    return sorted(hits, key=lambda h: h["score"], reverse=True)
