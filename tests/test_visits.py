"""Visitor counts: daily unique visitors from hashed IPs, page views, stats endpoint. No OpenAI."""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from agents.base import AgentResult
from api import deps
from main import app
from services import visits


class OneCentAgent:
    def run(self, question):
        return AgentResult(status="answered", routes=["quality"], answer="25.00 mm.", citations=[],
                           tokens=10, cost_usd=0.01)


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}")
    now = {"t": datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)}
    monkeypatch.setattr(visits, "_utcnow", lambda: now["t"])
    app.dependency_overrides[deps.get_agent] = lambda: OneCentAgent()
    with TestClient(app) as c:
        c.now = now
        yield c
    app.dependency_overrides.clear()


def _visit(c, ip):
    assert c.post("/visit", headers={"Fly-Client-IP": ip}).status_code == 204


def test_unique_visitors_and_page_views_per_day(client):
    for ip in ("1.1.1.1", "1.1.1.1", "2.2.2.2"):
        _visit(client, ip)
    client.now["t"] += timedelta(days=1)
    _visit(client, "1.1.1.1")
    body = client.get("/stats?days=7").json()
    days = {d["day"]: d for d in body["daily"]}
    assert days["2026-11-08"]["page_views"] == 3 and days["2026-11-08"]["unique_visitors"] == 2
    assert days["2026-11-09"]["page_views"] == 1 and days["2026-11-09"]["unique_visitors"] == 1
    assert body["totals"]["page_views"] == 4 and body["totals"]["visitor_days"] == 3


def test_no_raw_ip_is_stored_and_hashes_change_daily(client, tmp_path):
    import sqlite3

    _visit(client, "9.9.9.9")
    client.now["t"] += timedelta(days=1)
    _visit(client, "9.9.9.9")
    conn = sqlite3.connect(tmp_path / "test.db")
    rows = conn.execute("SELECT day, visitor FROM visits ORDER BY day").fetchall()
    dump = "\n".join(conn.iterdump())
    conn.close()
    assert "9.9.9.9" not in dump
    assert len(rows) == 2 and rows[0][1] != rows[1][1]  # same person, different hash each day


def test_stats_include_questions_and_cost(client):
    client.now["t"] = datetime.now(timezone.utc)  # the queries log uses the real clock
    _visit(client, "3.3.3.3")
    assert client.post("/ask", json={"question": "Tolerance for A-102?"}).status_code == 200
    today = client.get("/api/stats").json()["daily"][0]
    assert today["questions"] == 1 and today["cost_usd"] == 0.01 and today["unique_visitors"] == 1


def test_stats_window_is_validated(client):
    assert client.get("/stats?days=0").status_code == 422
    assert client.get("/stats?days=366").status_code == 422
