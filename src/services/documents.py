"""Business logic for knowledge sources: listing, re-indexing and retrieval."""

from __future__ import annotations

from api.schemas import (
    Citation,
    IngestResponse,
    IngestResult,
    SearchHit,
    SearchResponse,
    SourceInfo,
)
from rag import ingest as rag_ingest
from rag.config import SOURCES
from rag.llm import LLMClient
from rag.vector_store import VectorStore

_CITATION_FIELDS = ("source", "doc_no", "title", "section", "section_title", "page_start", "page_end")


def to_citation(metadata: dict) -> Citation:
    return Citation(**{k: metadata[k] for k in _CITATION_FIELDS})


def list_sources(store: VectorStore) -> list[SourceInfo]:
    return [
        SourceInfo(key=s.key, doc_no=s.doc_no, title=s.title, filename=s.filename, chunks=store.count(s.key))
        for s in SOURCES.values()
    ]


def vector_store_ready(store: VectorStore) -> bool:
    return all(store.count(key) > 0 for key in SOURCES)


def ingest_sources(sources: list[str] | None, llm: LLMClient, store: VectorStore) -> IngestResponse:
    reports = rag_ingest.ingest(sources, llm=llm, store=store)
    results = [IngestResult(**vars(r)) for r in reports]
    return IngestResponse(results=results, total_cost_usd=sum(r.cost_usd for r in results))


def search_documents(question: str, sources: list[str] | None, k: int, llm: LLMClient, store: VectorStore) -> SearchResponse:
    hits = rag_ingest.search(question, sources, k, llm=llm, store=store)
    return SearchResponse(
        question=question,
        hits=[
            SearchHit(text=h["text"], score=round(h["score"], 4), matched_by=h["matched_by"],
                      vector_score=h["vector_score"], keyword_score=h["keyword_score"],
                      citation=to_citation(h["metadata"]))
            for h in hits
        ],
    )
