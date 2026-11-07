"""Business logic for answering questions and for the query log / feedback."""

from __future__ import annotations

import sqlite3
import time

from agents.base import AnswerAgent
from api.schemas import (
    DEFAULT_CUSTOMER_ID,
    AskResponse,
    Citation,
    FeedbackRequest,
    QueryRecord,
    SessionMessage,
    SessionResponse,
    SessionSummary,
    Usage,
)
from persistence import queries as repo
from persistence import sessions as session_repo
from services.redact import redact
from services.session_agent import SessionAgent, SessionNotFoundError  # noqa: F401 (re-exported)


class QueryNotFoundError(LookupError):
    pass


def ask(question: str, agent: AnswerAgent, conn: sqlite3.Connection, *, session_id: str | None = None,
        customer_id: str = DEFAULT_CUSTOMER_ID) -> AskResponse:
    """Run the answer agent, log the result (FR8), store the exchange in the session and return it.

    Without a session_id, SessionAgent reuses the customer's active session or creates one.
    Nothing is stored if the agent raises, so only completed answers reach session history.
    """
    sessions = SessionAgent(conn)
    sessions.check_owner(customer_id, session_id)
    start = time.perf_counter()
    result = agent.run(question)
    latency_ms = int((time.perf_counter() - start) * 1000)
    citations = [Citation(**c) for c in result.citations]  # validates the agent's output
    session_id = sessions.resolve(customer_id, session_id).session["session_id"]
    query_id = repo.insert(
        conn,
        question=question,
        status=result.status,
        routes=list(result.routes),
        answer=result.answer,
        citations=[c.model_dump() for c in citations],
        flags=result.flags,
        confidence=result.confidence,
        trace=result.trace,
        tokens=result.tokens,
        cost_usd=result.cost_usd,
        latency_ms=latency_ms,
    )
    session_repo.add_exchange(
        conn,
        session_id=session_id,
        customer_id=customer_id,
        question=redact(question),
        answer=redact(result.answer),
        citations=[c.model_dump() for c in citations],
        confidence=result.confidence,
        status=result.status,
        query_id=query_id,
    )
    sessions.touch(session_id)
    return AskResponse(
        query_id=query_id,
        question=question,
        status=result.status,
        routes=result.routes,
        answer=result.answer,
        citations=citations,
        flags=result.flags,
        confidence=result.confidence,
        trace=result.trace,
        usage=Usage(tokens=result.tokens, cost_usd=result.cost_usd),
        latency_ms=latency_ms,
        session_id=session_id,
        customer_id=customer_id,
    )


def _session_response(session: dict, conn: sqlite3.Connection, created: bool = False) -> SessionResponse:
    rows = session_repo.list_messages(conn, session["session_id"])
    return SessionResponse(**session, created=created, messages=[SessionMessage(**r) for r in rows])


def get_session(conn: sqlite3.Connection, session_id: str) -> SessionResponse:
    session = session_repo.get_session(conn, session_id)
    if session is None:
        raise SessionNotFoundError(f"Session {session_id} not found")
    return _session_response(session, conn)


def active_session(conn: sqlite3.Connection, customer_id: str) -> SessionResponse:
    """Pull the customer's active session with its messages, or create a new empty one."""
    resolved = SessionAgent(conn).resolve(customer_id)
    return _session_response(resolved.session, conn, created=resolved.created)


def close_session(conn: sqlite3.Connection, customer_id: str, session_id: str) -> SessionResponse:
    """End a session. The customer's next question or active-session call starts a new one."""
    return _session_response(SessionAgent(conn).close(customer_id, session_id), conn)


def resume_session(conn: sqlite3.Connection, customer_id: str, session_id: str) -> SessionResponse:
    """Make an earlier session the customer's active one again."""
    return _session_response(SessionAgent(conn).resume(customer_id, session_id), conn)


def list_sessions(conn: sqlite3.Connection, customer_id: str, limit: int) -> list[SessionSummary]:
    return [SessionSummary(**r) for r in session_repo.list_sessions(conn, customer_id, limit)]


def _record(d: dict) -> QueryRecord:
    return QueryRecord(**d, usage=Usage(tokens=d["tokens"], cost_usd=d["cost_usd"]))


def recent_queries(conn: sqlite3.Connection, limit: int) -> list[QueryRecord]:
    return [_record(d) for d in repo.list_recent(conn, limit)]


def get_query(conn: sqlite3.Connection, query_id: int) -> QueryRecord:
    d = repo.get(conn, query_id)
    if d is None:
        raise QueryNotFoundError(f"Query {query_id} not found")
    return _record(d)


def add_feedback(conn: sqlite3.Connection, query_id: int, body: FeedbackRequest) -> QueryRecord:
    if not repo.set_feedback(conn, query_id, body.helpful, body.note):
        raise QueryNotFoundError(f"Query {query_id} not found")
    return get_query(conn, query_id)
