"""Customer session storage: mocked agent and temp SQLite. No OpenAI calls."""

import sqlite3

import pytest
from fastapi.testclient import TestClient

from agents.base import AgentResult
from api import deps
from main import app
from persistence.db import db_path
from services.redact import REDACTED, redact

CITATION = {
    "source": "quality", "doc_no": "QC-STD-200", "title": "Quality Control Standards",
    "section": "3.2", "section_title": "A-102 Shaft", "page_start": 4, "page_end": 4,
}


class FakeAgent:
    def __init__(self, answer="Diameter 25.00 mm +/- 0.02 for A-102 Rev F.", fail=None):
        self.answer, self.fail = answer, fail

    def run(self, question):
        if self.fail:
            raise self.fail
        return AgentResult(status="answered", routes=["quality"], answer=self.answer,
                           citations=[CITATION], confidence="high", tokens=50, cost_usd=0.0001)


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}")

    def _make(agent=None):
        app.dependency_overrides[deps.get_agent] = lambda: agent or FakeAgent()
        return TestClient(app)

    yield _make
    app.dependency_overrides.clear()


def test_ask_without_session_starts_one_with_default_customer(client):
    with client() as c:
        body = c.post("/ask", json={"question": "What is the A-102 diameter tolerance?"}).json()
        assert body["customer_id"] == "1" and len(body["session_id"]) == 32
        msgs = c.get(f"/sessions/{body['session_id']}").json()["messages"]
    assert [m["role"] for m in msgs] == ["user", "assistant"]
    user, bot = msgs
    assert user["message"] == "What is the A-102 diameter tolerance?" and user["answer"] is None
    assert bot["answer"] == body["answer"] and bot["citations"] == [CITATION]
    assert bot["confidence"] == "high" and bot["status"] == "answered"
    assert user["query_id"] == bot["query_id"] == body["query_id"]
    assert all(m["customer_id"] == "1" and m["created_at"] for m in msgs)


def test_session_accumulates_turns_in_order(client):
    with client() as c:
        for q in ("first question?", "second question?"):
            r = c.post("/ask", json={"question": q, "session_id": "shift-a_1", "customer_id": "cust-42"})
            assert r.status_code == 200 and r.json()["session_id"] == "shift-a_1"
        c.post("/ask", json={"question": "other session?", "session_id": "shift-b"})
        msgs = c.get("/sessions/shift-a_1").json()["messages"]
    assert [m["message"] for m in msgs if m["role"] == "user"] == ["first question?", "second question?"]
    assert len(msgs) == 4 and {m["customer_id"] for m in msgs} == {"cust-42"}


def test_failed_answer_is_not_stored(client):
    from rag.llm import LLMUnavailableError

    with client(FakeAgent(fail=LLMUnavailableError("down"))) as c:
        assert c.post("/ask", json={"question": "anything?", "session_id": "s1"}).status_code == 503
        assert c.get("/sessions/s1").status_code == 404


def test_unknown_session_returns_404(client):
    with client() as c:
        r = c.get("/sessions/nope")
    assert r.status_code == 404 and "not found" in r.json()["detail"]


@pytest.mark.parametrize("payload", [
    {"question": "valid question", "session_id": "bad id!"},
    {"question": "valid question", "customer_id": "jane@example.com"},
    {"question": "valid question", "session_id": "x" * 65},
])
def test_ids_must_be_opaque(client, payload):
    with client() as c:
        assert c.post("/ask", json=payload).status_code == 422


def test_secrets_and_contact_data_are_redacted_before_storage(client):
    question = "my key is sk-abcdefghijklmnop1234 email bob@plant.com call 555-123-4567 re A-102?"
    with client(FakeAgent(answer="Use token: abc123 for A-102 Rev F, torque 45 N-m.")) as c:
        body = c.post("/ask", json={"question": question, "session_id": "s2"}).json()
        msgs = c.get("/sessions/s2").json()["messages"]
    user, bot = msgs
    for secret in ("sk-abcdefghijklmnop1234", "bob@plant.com", "555-123-4567"):
        assert secret not in user["message"]
    assert "A-102" in user["message"] and "abc123" not in bot["answer"]
    assert "A-102 Rev F" in bot["answer"] and "45 N-m" in bot["answer"]
    assert body["answer"].startswith("Use token: abc123")  # live response is unchanged

    raw = sqlite3.connect(db_path()).execute("SELECT group_concat(message || answer) FROM session_messages").fetchone()
    assert raw[0] is None or "sk-abcdef" not in raw[0]


@pytest.mark.parametrize("text", ["Torque 45 N-m per MM-100 section 4.1, page 3", "A-102 Rev F, 25.00 +/- 0.02 mm",
                                  "Grease every 250 hours, 2 pumps"])
def test_redact_leaves_plant_data_alone(text):
    assert redact(text) == text


@pytest.mark.parametrize("text", ["Authorization: Bearer abcdefghijklmnop", "password=hunter2",
                                  "+1 (555) 123-4567", "AKIAABCDEFGHIJKLMNOP"])
def test_redact_catches_secrets(text):
    assert REDACTED in redact(text)


# ---- SessionAgent: reuse the active session, or create one
from datetime import datetime, timedelta, timezone  # noqa: E402

from services import session_agent  # noqa: E402


@pytest.fixture
def clock(monkeypatch):
    """Controllable UTC clock for the SessionAgent."""
    state = {"now": datetime(2026, 11, 6, 8, 0, tzinfo=timezone.utc)}
    monkeypatch.setattr(session_agent, "_utcnow", lambda: state["now"])

    def advance(minutes):
        state["now"] += timedelta(minutes=minutes)

    return advance


def test_active_session_is_created_then_pulled(client, clock):
    with client() as c:
        first = c.post("/sessions/active").json()
        assert first["created"] is True and first["customer_id"] == "1"
        assert first["status"] == "active" and first["messages"] == []

        clock(5)
        again = c.post("/sessions/active", json={"customer_id": "1"}).json()
    assert again["session_id"] == first["session_id"] and again["created"] is False


def test_ask_without_session_reuses_active_one(client, clock):
    with client() as c:
        sid = c.post("/ask", json={"question": "first question?"}).json()["session_id"]
        clock(10)
        assert c.post("/ask", json={"question": "second question?"}).json()["session_id"] == sid
        pulled = c.post("/sessions/active").json()
    assert pulled["session_id"] == sid and pulled["created"] is False
    assert [m["message"] for m in pulled["messages"] if m["role"] == "user"] == ["first question?", "second question?"]


def test_idle_session_is_closed_and_replaced(client, clock, monkeypatch):
    monkeypatch.setenv("SESSION_IDLE_MINUTES", "30")
    with client() as c:
        old = c.post("/ask", json={"question": "before break?"}).json()["session_id"]
        clock(31)
        new = c.post("/sessions/active").json()
        assert new["created"] is True and new["session_id"] != old and new["messages"] == []
        assert c.get(f"/sessions/{old}").json()["status"] == "closed"
        # an explicit session_id can still continue the old conversation
        r = c.post("/ask", json={"question": "back to it?", "session_id": old}).json()
        assert r["session_id"] == old and c.get(f"/sessions/{old}").json()["status"] == "active"


def test_sessions_are_per_customer(client, clock):
    with client() as c:
        a = c.post("/sessions/active", json={"customer_id": "1"}).json()["session_id"]
        b = c.post("/sessions/active", json={"customer_id": "2"}).json()["session_id"]
        assert a != b
        r = c.post("/ask", json={"question": "steal it?", "session_id": a, "customer_id": "2"})
    assert r.status_code == 409


def test_ticket_numbers_count_per_customer_and_never_change(client):
    with client() as c:
        first = c.post("/sessions/active", json={"customer_id": "1"}).json()
        other = c.post("/sessions/active", json={"customer_id": "2"}).json()
        assert first["ticket_no"] == 1001 and other["ticket_no"] == 1001
        closed = c.post(f"/sessions/{first['session_id']}/close", json={"customer_id": "1"}).json()
        assert closed["status"] == "closed" and closed["ticket_no"] == 1001
        second = c.post("/sessions/active", json={"customer_id": "1"}).json()
        assert second["created"] is True and second["ticket_no"] == 1002
        listed = {s["session_id"]: s["ticket_no"] for s in c.get("/sessions?customer_id=1").json()}
    assert listed == {first["session_id"]: 1001, second["session_id"]: 1002}


def test_mismatch_is_rejected_before_the_llm_runs(client):
    agent = FakeAgent()
    agent.run = lambda q: pytest.fail("agent should not run for another customer's session")
    with client(agent) as c:
        sid = c.post("/sessions/active", json={"customer_id": "1"}).json()["session_id"]
        assert c.post("/ask", json={"question": "valid question", "session_id": sid,
                                    "customer_id": "2"}).status_code == 409


def test_active_session_validates_customer_id(client):
    with client() as c:
        assert c.post("/sessions/active", json={"customer_id": "bob@x.com"}).status_code == 422


# ---- end, resume and list (used by the React app)
def test_end_session_then_next_question_starts_a_new_one(client, clock):
    with client() as c:
        old = c.post("/ask", json={"question": "first question?"}).json()["session_id"]
        closed = c.post(f"/sessions/{old}/close", json={"customer_id": "1"}).json()
        assert closed["status"] == "closed" and len(closed["messages"]) == 2
        new = c.post("/sessions/active").json()
        assert new["created"] is True and new["session_id"] != old
        assert c.post("/ask", json={"question": "next question?"}).json()["session_id"] == new["session_id"]


def test_resume_makes_previous_session_active_and_closes_current(client, clock):
    with client() as c:
        old = c.post("/ask", json={"question": "old question?"}).json()["session_id"]
        c.post(f"/sessions/{old}/close")
        current = c.post("/sessions/active").json()["session_id"]
        clock(1)
        resumed = c.post(f"/sessions/{old}/resume", json={"customer_id": "1"}).json()
        assert resumed["status"] == "active" and resumed["messages"][0]["message"] == "old question?"
        assert c.get(f"/sessions/{current}").json()["status"] == "closed"
        assert c.post("/sessions/active").json()["session_id"] == old
        assert c.post("/ask", json={"question": "follow up?"}).json()["session_id"] == old


def test_list_sessions_newest_first_with_summary(client, clock):
    with client() as c:
        a = c.post("/ask", json={"question": "about pumps?"}).json()["session_id"]
        c.post("/ask", json={"question": "and seals?"})
        c.post(f"/sessions/{a}/close")
        clock(1)
        b = c.post("/sessions/active").json()["session_id"]
        c.post("/sessions/active", json={"customer_id": "2"})
        rows = c.get("/sessions?customer_id=1").json()
    assert [r["session_id"] for r in rows] == [b, a]
    assert rows[0]["status"] == "active" and rows[0]["question_count"] == 0 and rows[0]["first_question"] is None
    assert rows[1]["status"] == "closed" and rows[1]["question_count"] == 2 and rows[1]["first_question"] == "about pumps?"


def test_close_and_resume_check_session_and_customer(client):
    with client() as c:
        sid = c.post("/sessions/active").json()["session_id"]
        assert c.post("/sessions/missing/close").status_code == 404
        assert c.post("/sessions/missing/resume").status_code == 404
        assert c.post(f"/sessions/{sid}/close", json={"customer_id": "2"}).status_code == 409
        assert c.post(f"/sessions/{sid}/resume", json={"customer_id": "2"}).status_code == 409
        assert c.get("/sessions?customer_id=bad id").status_code == 422


# ---- tickets: states, first-run demo seed, new / close / reopen flow
def _active(c, create=False):
    return c.post("/sessions/active", json={"customer_id": "1", "create": create}).json()


def _states(c):
    return {s["ticket_no"]: s["state"] for s in c.get("/sessions?customer_id=1").json()}


def test_first_run_seeds_five_demo_tickets_once(client, monkeypatch):
    monkeypatch.setenv("DEMO_TICKETS", "1")
    with client() as c:
        current = _active(c)
        assert current["ticket_no"] == 1001 and current["state"] == "open" and current["status"] == "active"
        assert _states(c) == {1001: "open", 1002: "on_hold", 1003: "escalated", 1004: "resolved", 1005: "closed"}
        resolved = next(s for s in c.get("/sessions?customer_id=1").json() if s["ticket_no"] == 1004)
        assert resolved["question_count"] == 2
    with client() as c:  # a restart doesn't seed again
        assert len(c.get("/sessions?customer_id=1").json()) == 5


def test_close_leaves_no_active_ticket_until_a_question_opens_one(client):
    with client() as c:
        first = _active(c, create=True)
        closed = c.post(f"/sessions/{first['session_id']}/close", json={"customer_id": "1"}).json()
        assert closed["state"] == "closed"
        assert _active(c) is None
        r = c.post("/ask", json={"question": "What tolerance for A-102?", "customer_id": "1"}).json()
        assert r["ticket_no"] == 1002 and _active(c)["session_id"] == r["session_id"]
    assert _states(c) == {1001: "closed", 1002: "open"}


def test_new_ticket_puts_the_open_one_on_hold_and_reopen_swaps_back(client):
    with client() as c:
        first = _active(c, create=True)
        second = c.post("/sessions/new", json={"customer_id": "1"}).json()
        assert second["ticket_no"] == 1002 and second["created"] is True
        assert _states(c) == {1001: "on_hold", 1002: "open"}
        reopened = c.post(f"/sessions/{first['session_id']}/resume", json={"customer_id": "1"}).json()
        assert reopened["state"] == "open" and _active(c)["ticket_no"] == 1001
        assert _states(c) == {1001: "open", 1002: "on_hold"}


def test_returning_user_gets_the_last_active_ticket_without_idle_timeout(client, clock):
    with client() as c:
        sid = _active(c, create=True)["session_id"]
        clock(60 * 24 * 3)  # three days later
        again = _active(c)
    assert again["session_id"] == sid and again["state"] == "open"


def test_old_database_gets_ticket_state_backfilled(tmp_path, monkeypatch):
    from persistence.db import connect, init_db

    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'old.db'}")
    conn = connect()
    conn.executescript(
        "CREATE TABLE sessions (session_id TEXT PRIMARY KEY, customer_id TEXT NOT NULL,"
        " status TEXT NOT NULL DEFAULT 'active', created_at TEXT NOT NULL, last_active_at TEXT NOT NULL);"
        "INSERT INTO sessions VALUES ('a', '1', 'closed', '2026-11-01T00:00:00Z', '2026-11-01T00:00:00Z');"
        "INSERT INTO sessions VALUES ('b', '1', 'active', '2026-11-02T00:00:00Z', '2026-11-02T00:00:00Z');"
    )
    init_db(conn)
    states = dict(conn.execute("SELECT session_id, state FROM sessions").fetchall())
    conn.close()
    assert states == {"a": "closed", "b": "open"}
