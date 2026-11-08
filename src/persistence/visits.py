"""Data access for visitor counts and app settings. Returns plain dicts and values."""

from __future__ import annotations

import secrets
import sqlite3


def salt(conn: sqlite3.Connection) -> str:
    """The secret used to hash visitor IPs; created once per database and never returned by the API."""
    row = conn.execute("SELECT value FROM app_meta WHERE key = 'visitor_salt'").fetchone()
    if row:
        return row[0]
    value = secrets.token_hex(16)
    conn.execute("INSERT OR IGNORE INTO app_meta (key, value) VALUES ('visitor_salt', ?)", (value,))
    conn.commit()
    return conn.execute("SELECT value FROM app_meta WHERE key = 'visitor_salt'").fetchone()[0]


def record(conn: sqlite3.Connection, day: str, visitor: str) -> None:
    conn.execute(
        "INSERT INTO visits (day, visitor, views) VALUES (?, ?, 1)"
        " ON CONFLICT (day, visitor) DO UPDATE SET views = views + 1",
        (day, visitor),
    )
    conn.commit()


def daily(conn: sqlite3.Connection, since_day: str) -> list[dict]:
    """Per day: page views, unique visitors, questions and OpenAI cost (newest first)."""
    rows = conn.execute(
        """
        WITH v AS (
            SELECT day, SUM(views) AS page_views, COUNT(*) AS unique_visitors
            FROM visits WHERE day >= ? GROUP BY day
        ),
        q AS (
            SELECT substr(created_at, 1, 10) AS day, COUNT(*) AS questions, SUM(cost_usd) AS cost_usd
            FROM queries WHERE substr(created_at, 1, 10) >= ? GROUP BY 1
        ),
        days AS (SELECT day FROM v UNION SELECT day FROM q)
        SELECT days.day,
               COALESCE(v.page_views, 0) AS page_views,
               COALESCE(v.unique_visitors, 0) AS unique_visitors,
               COALESCE(q.questions, 0) AS questions,
               ROUND(COALESCE(q.cost_usd, 0), 4) AS cost_usd
        FROM days LEFT JOIN v ON v.day = days.day LEFT JOIN q ON q.day = days.day
        ORDER BY days.day DESC
        """,
        (since_day, since_day),
    ).fetchall()
    return [dict(r) for r in rows]


def unique_visitors(conn: sqlite3.Connection, since_day: str) -> int:
    """Distinct visitor-days in the window (a visitor on two days counts twice: hashes change daily)."""
    return conn.execute("SELECT COUNT(*) FROM visits WHERE day >= ?", (since_day,)).fetchone()[0]
