"""First-run demo data: five tickets (#1001-#1005) for the demo customer, in different states.

Loaded by init_db only when the sessions table is empty, so it never touches real use. The answers
in demo_tickets.json are real agent outputs copied from the query log. DEMO_TICKETS=0 skips it.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

SEED_FILE = Path(__file__).with_name("demo_tickets.json")


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def seed_demo_tickets(conn: sqlite3.Connection, now: datetime | None = None) -> int:
    """Insert the demo tickets if there are no sessions yet. Returns how many were added."""
    if conn.execute("SELECT 1 FROM sessions LIMIT 1").fetchone():
        return 0
    data = json.loads(SEED_FILE.read_text())
    customer = data["customer_id"]
    now = now or datetime.now(timezone.utc)
    tickets = sorted(data["tickets"], key=lambda t: t["ticket_no"])  # rowid order sets the number
    with conn:
        for t in tickets:
            sid = f"demo-{t['ticket_no']}"
            last = now - timedelta(days=t["days_ago"])
            started = last - timedelta(minutes=5 * len(t["exchanges"]))
            status = "active" if t["state"] == "open" else "closed"
            conn.execute(
                "INSERT INTO sessions (session_id, customer_id, status, state, created_at, last_active_at)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (sid, customer, status, t["state"], _iso(started), _iso(last)),
            )
            for i, x in enumerate(t["exchanges"]):
                at = _iso(started + timedelta(minutes=5 * i))
                conn.execute(
                    "INSERT INTO session_messages (session_id, customer_id, role, message, status, created_at)"
                    " VALUES (?, ?, 'user', ?, ?, ?)",
                    (sid, customer, x["question"], x["status"], at),
                )
                conn.execute(
                    "INSERT INTO session_messages (session_id, customer_id, role, answer, citations,"
                    " confidence, status, created_at) VALUES (?, ?, 'assistant', ?, ?, ?, ?, ?)",
                    (sid, customer, x["answer"], json.dumps(x["citations"]), x["confidence"], x["status"], at),
                )
    return len(tickets)
