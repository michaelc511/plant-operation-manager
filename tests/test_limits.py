"""Usage limits for the public demo: rate limit, daily budget, ingest switch, /api routes. No OpenAI."""

import pytest
from fastapi.testclient import TestClient

from agents.base import AgentResult
from api import deps
from main import app
from services import limits

ASK = {"question": "How often do we grease the CV-3 bearings?"}


class CostlyAgent:
    """Each answer costs `cost` dollars, so the daily budget can be reached quickly."""

    def __init__(self, cost=0.0001):
        self.cost, self.calls = cost, 0

    def run(self, question):
        self.calls += 1
        return AgentResult(status="answered", routes=["maintenance"], answer="Every 250 operating hours.",
                           citations=[], tokens=100, cost_usd=self.cost)


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}")

    def _make(agent):
        app.dependency_overrides[deps.get_agent] = lambda: agent
        return TestClient(app)

    yield _make
    app.dependency_overrides.clear()


def test_rate_limit_per_minute_returns_429_before_the_llm_runs(client, monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "2")
    agent = CostlyAgent()
    with client(agent) as c:
        assert [c.post("/ask", json=ASK).status_code for _ in range(3)] == [200, 200, 429]
        r = c.post("/ask", json=ASK)
    assert r.status_code == 429 and "a minute" in r.json()["detail"]
    assert agent.calls == 2


def test_rate_limit_is_per_visitor_using_fly_client_ip(client, monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "1")
    with client(CostlyAgent()) as c:
        assert c.post("/ask", json=ASK, headers={"Fly-Client-IP": "1.1.1.1"}).status_code == 200
        assert c.post("/ask", json=ASK, headers={"Fly-Client-IP": "1.1.1.1"}).status_code == 429
        assert c.post("/ask", json=ASK, headers={"Fly-Client-IP": "2.2.2.2"}).status_code == 200


def test_daily_limit_and_minute_window(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "5")
    monkeypatch.setenv("RATE_LIMIT_PER_DAY", "3")
    t = 1_000_000.0
    for i in range(3):
        limits.check_rate("ip", now=t + i * 120)  # spread out: minute limit never hit
    with pytest.raises(limits.RateLimitedError, match="Daily limit of 3"):
        limits.check_rate("ip", now=t + 400)
    limits.check_rate("ip", now=t + 86400 + 10)  # a day later the oldest calls have expired


def test_daily_budget_blocks_paid_calls_once_spent(client, monkeypatch):
    monkeypatch.setenv("DAILY_BUDGET_USD", "0.01")
    agent = CostlyAgent(cost=0.006)
    with client(agent) as c:
        assert c.post("/ask", json=ASK).status_code == 200   # spent 0.006
        assert c.post("/ask", json=ASK).status_code == 200   # spent 0.012 (checked before this call)
        r = c.post("/ask", json=ASK)
        assert r.status_code == 429 and "daily question limit" in r.json()["detail"]
        assert c.post("/search", json={"question": "grease?"}).status_code == 429
        assert c.get("/health").status_code == 200           # free endpoints still work
    assert agent.calls == 2


def test_ingest_can_be_switched_off(client, monkeypatch):
    monkeypatch.setenv("ALLOW_INGEST", "0")
    with client(CostlyAgent()) as c:
        r = c.post("/sources/ingest", json={})
    assert r.status_code == 403 and "switched off" in r.json()["detail"]


def test_routes_are_also_served_under_api_prefix(client):
    with client(CostlyAgent()) as c:
        assert c.get("/api/health").status_code == 200
        r = c.post("/api/ask", json=ASK)
        assert r.status_code == 200 and r.json()["ticket_no"] == 1001
        assert c.post("/api/sessions/active", json={"customer_id": "1", "create": False}).status_code == 200
