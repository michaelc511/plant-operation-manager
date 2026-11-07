"""Mocked tests for BM25 keyword search and hybrid (vector + keyword) fusion. No OpenAI calls."""

from types import SimpleNamespace

import pytest

from rag.hybrid import HybridSearcher
from rag.ingest import ingest, search
from rag.keyword_index import BM25Index, tokenize
from rag.pdf_loader import Chunk


def test_tokenize_keeps_ids_whole_and_indexes_their_parts():
    assert tokenize("Lock out HP-400 at DS-3C") == ["lock", "out", "hp-400", "hp", "400", "ds-3c", "ds", "3c"]
    assert tokenize("section 5.4, form EHS-F-07") == ["section", "5.4", "5", "4", "form", "ehs-f-07", "ehs", "f", "07"]


def test_tokenize_drops_stopwords_and_folds_plurals():
    assert tokenize("How often do we grease the bearings?") == ["often", "grease", "bearing"]
    assert tokenize("glass") == ["glass"]  # -ss is not a plural


def test_bm25_ranks_exact_id_match_first():
    idx = BM25Index(
        ["a", "b", "c"],
        ["Replace filter FE-400-10 every 1,000 hours.", "Replace the intake filter FE-AC1-A.", "Grease the bearings."],
    )
    hits = idx.search("When do I change FE-400-10?", 3)
    assert hits[0][0] == "a"
    assert all(s > 0 for _, s in hits) and "c" not in [i for i, _ in hits]


def test_bm25_returns_nothing_for_unknown_terms():
    idx = BM25Index(["a"], ["Grease the bearings."])
    assert idx.search("xylophone quokka", 5) == []


# ---- fusion, with a stub vector store so vector ranks are controlled exactly

def _chunk(i, text):
    return Chunk(text=text, source="maintenance", doc_no="MM-100", title="M", section=str(i),
                 section_title=f"S{i}", page_start=1, page_end=1, chunk_index=i)


class StubStore:
    """Stands in for VectorStore: query() returns a fixed vector ranking; collection() serves BM25."""

    def __init__(self, chunks, vector_order, vector_scores=None):
        self.chunks = {f"maintenance-{c.chunk_index:04d}": c for c in chunks}
        self.order = vector_order
        self.scores = vector_scores or {cid: 0.9 - 0.1 * n for n, cid in enumerate(vector_order)}
        self.col_id = "v1"

    def query(self, source, vector, k):
        return [{"id": cid, "text": self.chunks[cid].text, "metadata": self.chunks[cid].to_metadata(),
                 "score": self.scores[cid]} for cid in self.order[:k]]

    def collection(self, source):
        ids = list(self.chunks)
        return SimpleNamespace(
            id=self.col_id, count=lambda: len(ids),
            get=lambda include: {"ids": ids, "documents": [self.chunks[i].text for i in ids],
                                 "metadatas": [self.chunks[i].to_metadata() for i in ids]},
        )


@pytest.fixture
def stub():
    chunks = [
        _chunk(0, "General lubrication schedule for conveyors and presses."),
        _chunk(1, "Replace return filter element FE-400-10 every 1,000 operating hours."),
        _chunk(2, "Conveyor belt tracking and tension checks."),
    ]
    # Vector search ranks the generic chunk first and the exact-ID chunk last.
    return StubStore(chunks, ["maintenance-0000", "maintenance-0002", "maintenance-0001"])


def test_hybrid_promotes_exact_keyword_match(stub):
    hits = HybridSearcher(stub, mode="hybrid").search("maintenance", "FE-400-10 filter", [0.0], k=3)
    assert hits[0].id == "maintenance-0001"
    assert hits[0].matched_by == "both" and hits[0].keyword_score > 0


def test_vector_mode_keeps_pure_vector_order(stub):
    hits = HybridSearcher(stub, mode="vector").search("maintenance", "FE-400-10 filter", [0.0], k=3)
    assert [h.id for h in hits] == stub.order
    assert all(h.matched_by == "vector" and h.keyword_score is None for h in hits)


def test_keyword_only_hit_survives_vector_threshold(stub):
    stub.scores = {"maintenance-0000": 0.5, "maintenance-0002": 0.4, "maintenance-0001": 0.1}
    hits = HybridSearcher(stub, mode="hybrid").search("maintenance", "FE-400-10", [0.0], k=3, min_vector_score=0.3)
    by_id = {h.id: h for h in hits}
    assert by_id["maintenance-0001"].matched_by == "keyword"  # below the vector cutoff, found by BM25
    assert by_id["maintenance-0001"].vector_score is None


def test_fused_scores_are_scaled_and_ordered(stub):
    hits = HybridSearcher(stub, mode="hybrid").search("maintenance", "conveyor", [0.0], k=3)
    scores = [h.score for h in hits]
    assert scores == sorted(scores, reverse=True)
    assert all(0 < s <= 1 for s in scores)


def test_keyword_index_rebuilds_after_reingest(stub):
    searcher = HybridSearcher(stub, mode="hybrid")
    assert searcher.search("maintenance", "quokka", [0.0], k=3)[0].matched_by == "vector"
    stub.chunks["maintenance-0002"] = _chunk(2, "Quokka-proof belt tracking.")
    stub.col_id = "v2"  # Chroma gives a re-created collection a new id
    hits = searcher.search("maintenance", "quokka", [0.0], k=3)
    assert any(h.id == "maintenance-0002" and h.keyword_score for h in hits)


# ---- end to end with the real PDFs, in-memory Chroma and fake embeddings

def test_search_finds_part_numbers_in_real_documents(llm, store):
    ingest(llm=llm, store=store)
    hits = search("FE-400-10", ["maintenance"], k=3, llm=llm, store=store)
    assert hits[0]["metadata"]["section"] in {"5.3", "12"}  # return filter section or spare parts list
    assert hits[0]["keyword_score"] is not None


def test_retrieval_agent_reports_hybrid_mix(llm, store):
    from agents.retrieval import RetrievalAgent

    ingest(["safety"], llm=llm, store=store)
    out = RetrievalAgent(llm, store)({"question": "EHS-F-07 incident form", "search_sources": ["safety"]})
    assert out["trace"][0].startswith("retrieval: hybrid search of ['safety']")
    assert any(e["metadata"]["section"] == "11" for e in out["evidence"])  # Incident reporting
    assert all("matched_by" in e["metadata"] for e in out["evidence"])
