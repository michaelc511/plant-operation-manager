"""Mocked tests for PDF chunking, the vector store and ingestion. No OpenAI calls."""

import pytest

from rag.config import CHUNK_CHARS, SOURCES
from rag.ingest import ingest, search
from rag.llm import LLMClient, MissingAPIKeyError
from rag.pdf_loader import load_chunks


@pytest.mark.parametrize("key", list(SOURCES))
def test_chunks_have_citation_metadata(key):
    chunks = load_chunks(SOURCES[key])
    assert len(chunks) > 10
    for c in chunks:
        assert c.source == key and c.doc_no == SOURCES[key].doc_no
        assert 1 <= c.page_start <= c.page_end
        assert c.section and c.section_title
        assert len(c.text) <= CHUNK_CHARS + 200  # body limit plus the context header
        assert "Page " not in c.text.splitlines()[-1]  # footers stripped
        assert "FICTIONAL SAMPLE DOCUMENT -" not in c.text


def test_sections_follow_document_numbering():
    sections = {c.section: c.section_title for c in load_chunks(SOURCES["safety"])}
    assert sections["5.2"] == "The Six-Step Lockout Procedure"
    # Numbered list items inside 5.2 must not be treated as headings.
    assert "6" in sections and sections["6"] == "Machine Guarding"


def test_known_fact_is_in_expected_section():
    chunks = load_chunks(SOURCES["maintenance"])
    hit = [c for c in chunks if "2 pumps (about 3 g) per bearing" in c.text]
    assert hit and hit[0].section == "4.1"


def test_ingest_builds_one_collection_per_source(llm, store):
    reports = ingest(llm=llm, store=store)
    assert {r.source for r in reports} == set(SOURCES)
    for r in reports:
        assert store.count(r.source) == r.chunks > 0
        assert r.tokens > 0


def test_reingest_one_source_is_idempotent(llm, store):
    ingest(llm=llm, store=store)
    before = store.count("quality")
    ingest(["quality"], llm=llm, store=store)
    assert store.count("quality") == before


def test_search_returns_ranked_hits_with_metadata(llm, store):
    ingest(llm=llm, store=store)
    hits = search("grease conveyor bearings pumps per bearing", ["maintenance"], k=3, llm=llm, store=store)
    assert len(hits) == 3
    assert hits[0]["score"] >= hits[-1]["score"]
    assert hits[0]["metadata"]["doc_no"] == "MM-100"


def test_missing_api_key_gives_clear_error(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(MissingAPIKeyError):
        LLMClient().embed(["hello"])
