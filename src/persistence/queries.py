"""Data access for the query log. Returns plain dicts; services map them to API models."""

from __future__ import annotations

import json
import sqlite3


def _row(r: sqlite3.Row) -> dict:
    d = dict(r)
    d["routes"] = json.loads(d["routes"])
    for key in ("citations", "flags", "trace"):
        d[key] = json.loads(d[key])
    d["helpful"] = None if d["helpful"] is None else bool(d["helpful"])
    return d


def insert(conn: sqlite3.Connection, *, question: str, status: str, routes: list, answer: str,
           citations: list, flags: list, confidence: str | None, trace: list,
           tokens: int, cost_usd: float, latency_ms: int) -> int:
    cur = conn.execute(
        "INSERT INTO queries (question, status, routes, answer, citations, flags, confidence, trace,"
        " tokens, cost_usd, latency_ms) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (question, status, json.dumps(routes), answer, json.dumps(citations), json.dumps(flags),
         confidence, json.dumps(trace), tokens, cost_usd, latency_ms),
    )
    conn.commit()
    return cur.lastrowid


def get(conn: sqlite3.Connection, query_id: int) -> dict | None:
    r = conn.execute("SELECT * FROM queries WHERE id = ?", (query_id,)).fetchone()
    return _row(r) if r else None


def list_recent(conn: sqlite3.Connection, limit: int) -> list[dict]:
    rows = conn.execute("SELECT * FROM queries ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    return [_row(r) for r in rows]


def set_feedback(conn: sqlite3.Connection, query_id: int, helpful: bool, note: str | None) -> bool:
    cur = conn.execute(
        "UPDATE queries SET helpful = ?, feedback_note = ? WHERE id = ?", (int(helpful), note, query_id)
    )
    conn.commit()
    return cur.rowcount == 1
