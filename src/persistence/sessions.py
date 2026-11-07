"""Data access for customer session storage. Returns plain dicts; services map them to API models."""

from __future__ import annotations

import json
import sqlite3


def _row(r: sqlite3.Row) -> dict:
    d = dict(r)
    d["citations"] = json.loads(d["citations"])
    return d


def add_exchange(conn: sqlite3.Connection, *, session_id: str, customer_id: str, question: str,
                 answer: str, citations: list, confidence: str | None, status: str,
                 query_id: int | None) -> None:
    """Store the user turn and the assistant turn together, in one transaction."""
    with conn:
        conn.execute(
            "INSERT INTO session_messages (session_id, customer_id, role, message, status, query_id)"
            " VALUES (?, ?, 'user', ?, ?, ?)",
            (session_id, customer_id, question, status, query_id),
        )
        conn.execute(
            "INSERT INTO session_messages (session_id, customer_id, role, answer, citations, confidence,"
            " status, query_id) VALUES (?, ?, 'assistant', ?, ?, ?, ?, ?)",
            (session_id, customer_id, answer, json.dumps(citations), confidence, status, query_id),
        )


def list_messages(conn: sqlite3.Connection, session_id: str) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM session_messages WHERE session_id = ? ORDER BY id", (session_id,)
    ).fetchall()
    return [_row(r) for r in rows]


# ---- session rows (one per conversation)
def get_session(conn: sqlite3.Connection, session_id: str) -> dict | None:
    r = conn.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,)).fetchone()
    return dict(r) if r else None


def latest_active(conn: sqlite3.Connection, customer_id: str, cutoff: str) -> dict | None:
    """The customer's most recently used active session, if it was used at or after `cutoff`."""
    r = conn.execute(
        "SELECT * FROM sessions WHERE customer_id = ? AND status = 'active' AND last_active_at >= ?"
        " ORDER BY last_active_at DESC, rowid DESC LIMIT 1",
        (customer_id, cutoff),
    ).fetchone()
    return dict(r) if r else None


def close_stale(conn: sqlite3.Connection, customer_id: str, cutoff: str) -> int:
    cur = conn.execute(
        "UPDATE sessions SET status = 'closed' WHERE customer_id = ? AND status = 'active' AND last_active_at < ?",
        (customer_id, cutoff),
    )
    conn.commit()
    return cur.rowcount


def create_session(conn: sqlite3.Connection, session_id: str, customer_id: str, now: str) -> dict:
    conn.execute(
        "INSERT INTO sessions (session_id, customer_id, status, created_at, last_active_at)"
        " VALUES (?, ?, 'active', ?, ?)",
        (session_id, customer_id, now, now),
    )
    conn.commit()
    return get_session(conn, session_id)


def touch(conn: sqlite3.Connection, session_id: str, now: str) -> None:
    conn.execute("UPDATE sessions SET status = 'active', last_active_at = ? WHERE session_id = ?", (now, session_id))
    conn.commit()


def close_session(conn: sqlite3.Connection, session_id: str) -> None:
    conn.execute("UPDATE sessions SET status = 'closed' WHERE session_id = ?", (session_id,))
    conn.commit()


def close_others(conn: sqlite3.Connection, customer_id: str, keep_session_id: str) -> None:
    """Keep at most one active session per customer."""
    conn.execute(
        "UPDATE sessions SET status = 'closed' WHERE customer_id = ? AND status = 'active' AND session_id != ?",
        (customer_id, keep_session_id),
    )
    conn.commit()


def list_sessions(conn: sqlite3.Connection, customer_id: str, limit: int) -> list[dict]:
    rows = conn.execute(
        "SELECT s.*,"
        " (SELECT COUNT(*) FROM session_messages m WHERE m.session_id = s.session_id AND m.role = 'user')"
        "   AS question_count,"
        " (SELECT m.message FROM session_messages m WHERE m.session_id = s.session_id AND m.role = 'user'"
        "   ORDER BY m.id LIMIT 1) AS first_question"
        " FROM sessions s WHERE s.customer_id = ? ORDER BY s.last_active_at DESC, s.rowid DESC LIMIT ?",
        (customer_id, limit),
    ).fetchall()
    return [dict(r) for r in rows]
