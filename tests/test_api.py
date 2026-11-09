"""Mocked API tests: fake embeddings, in-memory Chroma, temp SQLite, fake agent. No OpenAI calls."""

import pytest
from fastapi.testclient import TestClient

from agents.base import AgentResult, NotConfiguredAgent
from api import deps
from main import app
from rag.ingest import ingest

CITATION = {
    "source": "maintenance", "doc_no": "MM-100", "title": "Equipment Maintenance Manual",
    "section": "4.1", "section_title": "Bearing Lubrication", "page_start": 3, "page_end": 3,
}


class FakeAgent:
    def __init__(self):
        self.questions = []

    def run(self, question):
        self.questions.append(question)
        return AgentResult(
            status="answered", routes=["maintenance"],
            answer="Every 250 operating hours, 2 pumps per bearing.",
            citations=[CITATION], tokens=120, cost_usd=0.0001,
        )


@pytest.fixture
def make_client(tmp_path, monkeypatch, llm, store):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}")

    def _make(agent=None, ingested=True):
        if ingested:
            ingest(llm=llm, store=store)
        app.dependency_overrides[deps.get_llm] = lambda: llm
        app.dependency_overrides[deps.get_store] = lambda: store
        app.dependency_overrides[deps.get_agent] = lambda: agent or FakeAgent()
        return TestClient(app)

    yield _make
    app.dependency_overrides.clear()


def test_health_reports_store_and_agent_status(make_client):
    with make_client(agent=NotConfiguredAgent(), ingested=False) as c:
        assert c.get("/health").json() == {"status": "ok", "vector_store_ready": False, "agent_ready": False}
    with make_client() as c:
        body = c.get("/health").json()
        assert body["vector_store_ready"] is True and body["agent_ready"] is True


def test_sources_lists_chunk_counts(make_client):
    with make_client() as c:
        body = c.get("/sources").json()
    assert {s["key"] for s in body} == {"safety", "maintenance", "quality"}
    assert all(s["chunks"] > 0 for s in body)


def test_ingest_one_source(make_client):
    with make_client(ingested=False) as c:
        r = c.post("/sources/ingest", json={"sources": ["quality"]})
    assert r.status_code == 200
    assert [x["source"] for x in r.json()["results"]] == ["quality"]


def test_ingest_rejects_unknown_source(make_client):
    with make_client(ingested=False) as c:
        r = c.post("/sources/ingest", json={"sources": ["hr"]})
    assert r.status_code == 422


def test_search_returns_hits_with_citations(make_client):
    with make_client() as c:
        r = c.post("/search", json={"question": "grease conveyor bearings", "sources": ["maintenance"], "k": 2})
    assert r.status_code == 200
    hits = r.json()["hits"]
    assert len(hits) == 2 and hits[0]["citation"]["doc_no"] == "MM-100"


@pytest.mark.parametrize("payload", [{"question": "  "}, {"question": "ok", "k": 1}, {"question": "valid question", "k": 50}])
def test_search_validates_input(make_client, payload):
    with make_client(ingested=False) as c:
        assert c.post("/search", json=payload).status_code == 422


def test_ask_returns_501_until_agent_is_built(make_client):
    with make_client(agent=NotConfiguredAgent(), ingested=False) as c:
        r = c.post("/ask", json={"question": "How often do we grease CV-3?"})
    assert r.status_code == 501
    assert "not configured" in r.json()["detail"]


def test_ask_logs_query_and_accepts_feedback(make_client):
    agent = FakeAgent()
    with make_client(agent=agent, ingested=False) as c:
        r = c.post("/ask", json={"question": "  How often   do we grease CV-3? "})
        assert r.status_code == 200
        body = r.json()
        assert agent.questions == ["How often do we grease CV-3?"]  # whitespace normalized
        assert body["routes"] == ["maintenance"] and body["citations"][0]["section"] == "4.1"
        qid = body["query_id"]

        logged = c.get(f"/queries/{qid}").json()
        assert logged["answer"] == body["answer"] and logged["helpful"] is None

        fb = c.post(f"/queries/{qid}/feedback", json={"helpful": False, "note": "missing torque"})
        assert fb.status_code == 200 and fb.json()["helpful"] is False

        recent = c.get("/queries?limit=5").json()
        assert recent[0]["id"] == qid and recent[0]["feedback_note"] == "missing torque"


def test_unknown_query_returns_404(make_client):
    with make_client(ingested=False) as c:
        assert c.get("/queries/999").status_code == 404
        assert c.post("/queries/999/feedback", json={"helpful": True}).status_code == 404


def test_missing_api_key_returns_503(make_client, monkeypatch):
    from rag.llm import LLMClient

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with make_client(ingested=False) as c:
        app.dependency_overrides[deps.get_llm] = lambda: LLMClient()
        r = c.post("/search", json={"question": "what PPE for PW-1?"})
    assert r.status_code == 503 and "OPENAI_API_KEY" in r.json()["detail"]


def test_source_pdf_opens_inline(make_client):
    with make_client(ingested=False) as c:
        r = c.get("/api/sources/maintenance/pdf")
        assert r.status_code == 200
        assert r.headers["content-type"] == "application/pdf"
        assert r.headers["content-disposition"].startswith("inline")
        assert "maintenance_manual.pdf" in r.headers["content-disposition"]
        assert r.content[:4] == b"%PDF"


def test_source_pdf_unknown_or_bad_key(make_client):
    with make_client(ingested=False) as c:
        assert c.get("/sources/nope/pdf").status_code == 404
        assert c.get("/sources/..%2F.env/pdf").status_code in (404, 422)
