"""SessionAgent: finds a customer's active session (ticket) or creates one. Plain code, no LLM call.

    current(customer_id)              -> the last active ticket, or None (never creates one)
    resolve(customer_id)              -> the last active ticket, or a new one if there is none
    resolve(customer_id, session_id)  -> continue that ticket (create it if it's new)
    new(customer_id)                  -> open a new ticket; the previous one goes on hold
    close(customer_id, session_id)    -> close it (state 'closed'); nothing is active until the
                                         customer opens a new ticket, asks, or reopens one
    resume(customer_id, session_id)   -> reopen an earlier ticket as the active one

A customer has at most one active ticket: whichever is resolved, created or resumed becomes active
and any other goes on hold. A session that belongs to another customer raises
SessionCustomerMismatchError (HTTP 409). Returning users get their last active ticket back; set
SESSION_IDLE_MINUTES to put tickets idle longer than that on hold instead (off by default).
"""

from __future__ import annotations

import os
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from persistence import sessions as repo

DEFAULT_IDLE_MINUTES = None  # no idle timeout: the last active ticket is kept


class SessionNotFoundError(LookupError):
    pass


class SessionCustomerMismatchError(PermissionError):
    pass


def _utcnow() -> datetime:  # patched in tests
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def idle_minutes() -> int | None:
    """Idle window in minutes, or None for no timeout (unset, 0 or invalid)."""
    try:
        minutes = int(os.getenv("SESSION_IDLE_MINUTES", "0"))
    except ValueError:
        return DEFAULT_IDLE_MINUTES
    return minutes if minutes > 0 else DEFAULT_IDLE_MINUTES


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

        active = self.current(customer_id)
        if active:
            return ResolvedSession(active, created=False)
        return self._create(customer_id, uuid.uuid4().hex, now)

    def current(self, customer_id: str) -> dict | None:
        """The customer's last active ticket, or None. Tickets past the idle window go on hold."""
        minutes = idle_minutes()
        cutoff = _iso(_utcnow() - timedelta(minutes=minutes)) if minutes else None
        active = repo.latest_active(self.conn, customer_id, cutoff)
        if active:
            repo.close_others(self.conn, customer_id, active["session_id"])
            return active
        if cutoff:
            repo.close_stale(self.conn, customer_id, cutoff)
        return None

    def new(self, customer_id: str) -> dict:
        return self._create(customer_id, uuid.uuid4().hex, _utcnow()).session

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
