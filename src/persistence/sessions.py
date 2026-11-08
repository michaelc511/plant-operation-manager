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
TICKET_BASE = 1000
# Ticket number shown to users instead of the session ID: the customer's 1st session is #1001, the
# 2nd #1002, ... Sessions are never deleted, so the number for a session never changes.
_TICKET_NO = (
    f" {TICKET_BASE} + (SELECT COUNT(*) FROM sessions t"
    " WHERE t.customer_id = s.customer_id AND t.rowid <= s.rowid) AS ticket_no"
)


# A ticket the customer switched away from (not closed by them) goes on hold.
_HOLD = "state = CASE WHEN state = 'open' THEN 'on_hold' ELSE state END"


def get_session(conn: sqlite3.Connection, session_id: str) -> dict | None:
    r = conn.execute(f"SELECT s.*,{_TICKET_NO} FROM sessions s WHERE s.session_id = ?", (session_id,)).fetchone()
    return dict(r) if r else None


def latest_active(conn: sqlite3.Connection, customer_id: str, cutoff: str | None = None) -> dict | None:
    """The customer's most recently used active session (used at or after `cutoff`, if given)."""
    r = conn.execute(
        f"SELECT s.*,{_TICKET_NO} FROM sessions s"
        " WHERE s.customer_id = ? AND s.status = 'active' AND s.last_active_at >= ?"
        " ORDER BY s.last_active_at DESC, s.rowid DESC LIMIT 1",
        (customer_id, cutoff or ""),
    ).fetchone()
    return dict(r) if r else None


def close_stale(conn: sqlite3.Connection, customer_id: str, cutoff: str) -> int:
    cur = conn.execute(
        f"UPDATE sessions SET status = 'closed', {_HOLD} WHERE customer_id = ? AND status = 'active'"
        " AND last_active_at < ?",
        (customer_id, cutoff),
    )
    conn.commit()
    return cur.rowcount


def create_session(conn: sqlite3.Connection, session_id: str, customer_id: str, now: str) -> dict:
    conn.execute(
        "INSERT INTO sessions (session_id, customer_id, status, state, created_at, last_active_at)"
        " VALUES (?, ?, 'active', 'open', ?, ?)",
        (session_id, customer_id, now, now),
    )
    conn.commit()
    return get_session(conn, session_id)


def touch(conn: sqlite3.Connection, session_id: str, now: str) -> None:
    conn.execute(
        "UPDATE sessions SET status = 'active', state = 'open', last_active_at = ? WHERE session_id = ?",
        (now, session_id),
    )
    conn.commit()


def close_session(conn: sqlite3.Connection, session_id: str) -> None:
    conn.execute("UPDATE sessions SET status = 'closed', state = 'closed' WHERE session_id = ?", (session_id,))
    conn.commit()


def close_others(conn: sqlite3.Connection, customer_id: str, keep_session_id: str) -> None:
    """Keep at most one active session per customer. The others go on hold (state kept if set by staff)."""
    conn.execute(
        f"UPDATE sessions SET status = 'closed', {_HOLD}"
        " WHERE customer_id = ? AND status = 'active' AND session_id != ?",
        (customer_id, keep_session_id),
    )
    conn.commit()


def list_sessions(conn: sqlite3.Connection, customer_id: str, limit: int) -> list[dict]:
    rows = conn.execute(
        f"SELECT s.*,{_TICKET_NO},"
        " (SELECT COUNT(*) FROM session_messages m WHERE m.session_id = s.session_id AND m.role = 'user')"
        "   AS question_count,"
        " (SELECT m.message FROM session_messages m WHERE m.session_id = s.session_id AND m.role = 'user'"
        "   ORDER BY m.id LIMIT 1) AS first_question"
        " FROM sessions s WHERE s.customer_id = ? ORDER BY s.last_active_at DESC, s.rowid DESC LIMIT ?",
        (customer_id, limit),
    ).fetchall()
    return [dict(r) for r in rows]
