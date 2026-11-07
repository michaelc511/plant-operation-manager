"""Mocked tests for the LangGraph orchestrator and its subagents. No OpenAI calls.

The fake chat model is scripted per test: `router` returns the router JSON, and `verifier`
is a function of the evidence it receives, so tests control every branch of the graph.
"""

import json
import re
import sqlite3
from types import SimpleNamespace

import pytest

import agents.retrieval as retrieval_mod
from agents.orchestrator import PlantQAAgent
from agents.verifier import NOT_FOUND_TEXT, check
from conftest import FakeEmbeddings
from persistence.db import init_db
from rag.ingest import ingest
from rag.llm import LLMClient

EVIDENCE_TAG = re.compile(r'<evidence id="(E\d+)" doc="([^"]+)"')


def route(category="in_scope", sources=(), safety=False, clarify=""):
    return {"category": category, "sources": list(sources), "safety_relevant": safety,
            "clarifying_question": clarify, "reasoning": "test"}


def cite_doc(doc_no, status="answered", extra_ids=(), supported=True, confidence="high"):
    """Verifier fake: answers citing the first passage from doc_no (plus any extra ids)."""
    def _verify(evidence):
        ids = [eid for eid, doc in evidence if doc == doc_no][:1] + list(extra_ids)
        marks = "".join(f"[{i}]" for i in ids)
        return {"status": status, "answer": f"Grease every 250 operating hours. {marks}".strip(),
                "claims": [{"claim": "Grease every 250 operating hours.", "evidence_ids": ids, "supported": supported}],
                "uncertainties": [], "follow_up_question": "", "confidence": confidence}
    return _verify


class FakeChat:
    def __init__(self, router, verifier=None):
        self.router = router
        self.verifiers = verifier if isinstance(verifier, list) else [verifier]
        self.calls = {"route": 0, "verified_answer": 0}
        self.verifier_inputs = []

    def create(self, model, temperature, messages, response_format):
        name = response_format["json_schema"]["name"]
        self.calls[name] += 1
        if name == "route":
            data = self.router
        else:
            evidence = EVIDENCE_TAG.findall(messages[1]["content"])
            self.verifier_inputs.append(evidence)
            fn = self.verifiers[min(self.calls[name], len(self.verifiers)) - 1]
            data = fn(evidence)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(data), refusal=None))],
            usage=SimpleNamespace(prompt_tokens=100, completion_tokens=20),
        )


@pytest.fixture
def indexed_store(llm, store):
    ingest(llm=llm, store=store)
    return store


@pytest.fixture(autouse=True)
def keep_all_hits(monkeypatch):
    # Fake bag-of-words embeddings give low similarity scores; don't filter them out.
    monkeypatch.setattr(retrieval_mod, "MIN_SCORE", -1.0)


def make_agent(store, chat):
    llm = LLMClient(client=SimpleNamespace(embeddings=FakeEmbeddings(), chat=SimpleNamespace(completions=chat)))
    return PlantQAAgent(llm, store)


def test_answered_question_is_routed_retrieved_and_cited(indexed_store):
    chat = FakeChat(route(sources=["maintenance"]), cite_doc("MM-100"))
    r = make_agent(indexed_store, chat).run("How often do we grease the CV-3 bearings?")
    assert r.status == "answered" and r.confidence == "high"
    assert r.routes == ["maintenance"]
    assert [c["doc_no"] for c in r.citations] == ["MM-100"]
    assert r.answer.endswith("[1]")  # [E#] markers renumbered to citation order
    assert r.flags == []
    assert [t.split(":")[0] for t in r.trace if not t.startswith("orchestrator")] == ["router", "retrieval", "verifier"]
    assert r.tokens > 0 and r.cost_usd > 0


def test_retrieval_only_searches_routed_source(indexed_store):
    chat = FakeChat(route(sources=["quality"]), cite_doc("QC-STD-200"))
    make_agent(indexed_store, chat).run("What is the A-102 journal tolerance?")
    docs = {doc for _, doc in chat.verifier_inputs[0]}
    assert docs == {"QC-STD-200"}


def test_out_of_scope_skips_retrieval_and_verifier(indexed_store):
    chat = FakeChat(route("out_of_scope"))
    r = make_agent(indexed_store, chat).run("When is payday?")
    assert r.status == "out_of_scope" and r.routes == ["out_of_scope"]
    assert chat.calls == {"route": 1, "verified_answer": 0}
    assert not any(t.startswith("retrieval") for t in r.trace)


def test_vague_question_asks_for_clarification(indexed_store):
    chat = FakeChat(route("clarify", clarify="Which part number?"))
    r = make_agent(indexed_store, chat).run("What's the spec?")
    assert r.status == "clarify" and r.answer == "Which part number?"
    assert chat.calls["verified_answer"] == 0


def test_safety_relevant_question_always_searches_safety(indexed_store):
    chat = FakeChat(route(sources=["maintenance"], safety=True), cite_doc("MM-100"))
    r = make_agent(indexed_store, chat).run("Can I replace the CV-3 guard while the line runs?")
    assert r.routes == ["maintenance", "safety"]
    assert {doc for _, doc in chat.verifier_inputs[0]} == {"EHS-SOP-001", "MM-100"}
    # Answer cited only maintenance, so the verifier flags the missing safety citation.
    assert any("no safety procedure was cited" in f for f in r.flags)
    assert r.confidence == "medium"


def test_safety_citation_clears_the_safety_flag(indexed_store):
    chat = FakeChat(route(sources=["maintenance"], safety=True), cite_doc("EHS-SOP-001"))
    r = make_agent(indexed_store, chat).run("Can I replace the CV-3 guard while the line runs?")
    assert not any("safety procedure" in f for f in r.flags)


def test_hallucinated_and_unsupported_citations_are_flagged(indexed_store):
    chat = FakeChat(route(sources=["maintenance"]), cite_doc("MM-100", extra_ids=["E99"], supported=False))
    r = make_agent(indexed_store, chat).run("How often do we grease CV-3?")
    assert "[E99]" not in r.answer and "E99" not in json.dumps(r.citations)
    assert any("not retrieved: E99" in f for f in r.flags)
    assert any(f.startswith("Not confirmed by the documents") for f in r.flags)
    assert r.confidence == "low"


def test_answer_without_valid_citations_is_withheld(indexed_store):
    chat = FakeChat(route(sources=["maintenance"]), cite_doc("NO-SUCH-DOC"))
    r = make_agent(indexed_store, chat).run("How often do we grease CV-3?")
    assert r.status == "not_found" and r.answer == NOT_FOUND_TEXT and r.citations == []


def test_verifier_not_found_widens_search_once(indexed_store):
    chat = FakeChat(route(sources=["quality"]),
                    [cite_doc("QC-STD-200", status="not_found"), cite_doc("MM-100")])
    r = make_agent(indexed_store, chat).run("How often do we grease CV-3?")
    assert chat.calls["verified_answer"] == 2
    assert r.status == "answered" and r.citations[0]["doc_no"] == "MM-100"
    assert r.routes == ["maintenance", "quality", "safety"]
    assert any("other sources were searched" in f for f in r.flags)


def test_no_evidence_anywhere_returns_not_found(indexed_store, monkeypatch):
    monkeypatch.setattr(retrieval_mod, "MIN_SCORE", 2.0)  # no vector match passes
    chat = FakeChat(route(sources=["safety"]))
    r = make_agent(indexed_store, chat).run("Xylophone zebra quokka?")  # and no keyword matches
    assert r.status == "not_found" and chat.calls["verified_answer"] == 0
    assert sum(t.startswith("retrieval") for t in r.trace) == 2  # routed pass + widened pass


def test_check_renumbers_markers_in_citation_order():
    evidence = [{"id": f"E{i}", "metadata": {"source": "quality", "doc_no": "QC-STD-200", "title": "Q",
                 "section": str(i), "section_title": "S", "page_start": 1, "page_end": 1}} for i in (1, 2, 3)]
    draft = {"status": "answered", "answer": "A [E3]. B [E1][E3].", "claims": [], "uncertainties": [],
             "follow_up_question": "", "confidence": "high"}
    v = check(draft, evidence, safety_relevant=False)
    assert v["answer"] == "A [1]. B [2][1]."
    assert [c["section"] for c in v["citations"]] == ["3", "1"]


def test_check_merges_chunks_from_the_same_section():
    meta = {"source": "maintenance", "doc_no": "MM-100", "title": "M", "section": "3",
            "section_title": "PM Schedule", "page_start": 3, "page_end": 3}
    evidence = [{"id": "E1", "metadata": meta}, {"id": "E2", "metadata": dict(meta)}]
    draft = {"status": "answered", "answer": "Weekly [E1][E2].", "claims": [], "uncertainties": [],
             "follow_up_question": "", "confidence": "high"}
    v = check(draft, evidence, safety_relevant=False)
    assert v["answer"] == "Weekly [1]." and len(v["citations"]) == 1


def test_check_uses_claim_evidence_when_answer_has_no_markers():
    evidence = [{"id": "E1", "metadata": {"source": "safety", "doc_no": "EHS-SOP-001", "title": "S",
                 "section": "8.1", "section_title": "Hot Work Permit", "page_start": 5, "page_end": 5}}]
    draft = {"status": "answered", "answer": "The fire watch stays 30 minutes after the work ends.",
             "claims": [{"claim": "30 minutes", "evidence_ids": ["E1"], "supported": True}],
             "uncertainties": [], "follow_up_question": "", "confidence": "high"}
    v = check(draft, evidence, safety_relevant=False)
    assert v["status"] == "answered" and v["answer"].endswith("[1]")
    assert v["citations"][0]["section"] == "8.1" and v["flags"] == []


def test_init_db_migrates_old_schema(tmp_path):
    conn = sqlite3.connect(tmp_path / "old.db")
    conn.row_factory = sqlite3.Row
    conn.execute(  # the first released schema, before flags/confidence/trace
        "CREATE TABLE queries (id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL DEFAULT '',"
        " question TEXT NOT NULL, status TEXT NOT NULL, routes TEXT NOT NULL, answer TEXT NOT NULL,"
        " citations TEXT NOT NULL, tokens INTEGER NOT NULL DEFAULT 0, cost_usd REAL NOT NULL DEFAULT 0,"
        " latency_ms INTEGER NOT NULL DEFAULT 0, helpful INTEGER, feedback_note TEXT)"
    )
    init_db(conn)
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(queries)")}
    assert {"flags", "confidence", "trace"} <= cols
