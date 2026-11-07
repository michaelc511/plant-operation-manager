"""SessionAgent: finds a customer's active session or creates one. Plain code, no LLM call.

    resolve(customer_id)              -> active session used within the idle window? reuse it
                                         otherwise close stale ones and create a new session
    resolve(customer_id, session_id)  -> continue that session (create it if it's new)
    close(customer_id, session_id)    -> end it; the next resolve() starts a new session
    resume(customer_id, session_id)   -> make an earlier session the active one again

A customer has at most one active session: whichever session is resolved or resumed becomes the
active one and any other is closed. A session that belongs to another customer raises
SessionCustomerMismatchError (HTTP 409). The idle window is SESSION_IDLE_MINUTES (default 30).
"""

from __future__ import annotations

import os
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from persistence import sessions as repo

DEFAULT_IDLE_MINUTES = 30


class SessionNotFoundError(LookupError):
    pass


class SessionCustomerMismatchError(PermissionError):
    pass


def _utcnow() -> datetime:  # patched in tests
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def idle_minutes() -> int:
    try:
        return max(1, int(os.getenv("SESSION_IDLE_MINUTES", DEFAULT_IDLE_MINUTES)))
    except ValueError:
        return DEFAULT_IDLE_MINUTES


@dataclass
class ResolvedSession:
    session: dict
    created: bool


class SessionAgent:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def resolve(self, customer_id: str, session_id: str | None = None) -> ResolvedSession:
        now = _utcnow()
        if session_id:
            existing = self._owned(customer_id, session_id, required=False)
            if existing is None:
                return self._create(customer_id, session_id, now)
            return ResolvedSession(self._activate(customer_id, session_id, now), created=False)

        cutoff = _iso(now - timedelta(minutes=idle_minutes()))
        active = repo.latest_active(self.conn, customer_id, cutoff)
        if active:
            repo.close_others(self.conn, customer_id, active["session_id"])
            return ResolvedSession(active, created=False)
        repo.close_stale(self.conn, customer_id, cutoff)
        return self._create(customer_id, uuid.uuid4().hex, now)

    def close(self, customer_id: str, session_id: str) -> dict:
        self._owned(customer_id, session_id)
        repo.close_session(self.conn, session_id)
        return repo.get_session(self.conn, session_id)

    def resume(self, customer_id: str, session_id: str) -> dict:
        self._owned(customer_id, session_id)
        return self._activate(customer_id, session_id, _utcnow())

    def check_owner(self, customer_id: str, session_id: str | None) -> None:
        """Fail fast (before any LLM spend) if an existing session belongs to someone else."""
        if session_id:
            self._owned(customer_id, session_id, required=False)

    def touch(self, session_id: str) -> None:
        """Mark the session as used now (keeps it active)."""
        repo.touch(self.conn, session_id, _iso(_utcnow()))

    # ---- helpers
    def _owned(self, customer_id: str, session_id: str, required: bool = True) -> dict | None:
        existing = repo.get_session(self.conn, session_id)
        if existing is None:
            if required:
                raise SessionNotFoundError(f"Session {session_id} not found")
            return None
        if existing["customer_id"] != customer_id:
            raise SessionCustomerMismatchError(f"Session {session_id} belongs to a different customer")
        return existing

    def _create(self, customer_id: str, session_id: str, now: datetime) -> ResolvedSession:
        session = repo.create_session(self.conn, session_id, customer_id, _iso(now))
        repo.close_others(self.conn, customer_id, session_id)
        return ResolvedSession(session, created=True)

    def _activate(self, customer_id: str, session_id: str, now: datetime) -> dict:
        repo.touch(self.conn, session_id, _iso(now))
        repo.close_others(self.conn, customer_id, session_id)
        return repo.get_session(self.conn, session_id)
