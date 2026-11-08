"""Visitor counts without third-party analytics or stored IPs. Plain code, no LLM call.

    record_visit(conn, ip)  -> called once per page load by the UI (POST /visit)
    stats(conn, days)       -> per-day page views, unique visitors, questions and OpenAI cost

A visitor is sha256(salt | day | ip), truncated: the salt is a random secret kept in the database,
so hashes can't be reversed, and the day is part of the hash, so a visitor can't be followed from
one day to the next. "Unique visitors" is therefore unique per day.
"""

from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime, timedelta, timezone

from persistence import visits as repo


def _utcnow() -> datetime:  # patched in tests
    return datetime.now(timezone.utc)


def visitor_hash(salt: str, day: str, ip: str) -> str:
    return hashlib.sha256(f"{salt}|{day}|{ip}".encode()).hexdigest()[:16]


def record_visit(conn: sqlite3.Connection, ip: str) -> None:
    day = _utcnow().strftime("%Y-%m-%d")
    repo.record(conn, day, visitor_hash(repo.salt(conn), day, ip))


def stats(conn: sqlite3.Connection, days: int = 30) -> dict:
    since = (_utcnow() - timedelta(days=days - 1)).strftime("%Y-%m-%d")
    rows = repo.daily(conn, since)
    return {
        "days": days,
        "totals": {
            "page_views": sum(r["page_views"] for r in rows),
            "visitor_days": sum(r["unique_visitors"] for r in rows),
            "questions": sum(r["questions"] for r in rows),
            "cost_usd": round(sum(r["cost_usd"] for r in rows), 4),
        },
        "daily": rows,
    }
