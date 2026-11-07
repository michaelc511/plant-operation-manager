"""HTTP routes. Thin: validate input, call a service, map errors to status codes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Path, Query

from agents.base import AgentNotConfiguredError, NotConfiguredAgent
from api.deps import get_agent, get_db, get_llm, get_store
from api.schemas import (
    CustomerRequest,
    AskRequest,
    AskResponse,
    FeedbackRequest,
    DEFAULT_CUSTOMER_ID,
    ID_PATTERN,
    HealthResponse,
    IngestRequest,
    IngestResponse,
    QueryRecord,
    SearchRequest,
    SearchResponse,
    SessionResponse,
    SessionSummary,
    SourceInfo,
)
from rag.llm import LLMUnavailableError, MissingAPIKeyError
from services import ask as ask_service
from services import documents
from services.session_agent import SessionCustomerMismatchError

router = APIRouter()


def _llm_unavailable(exc: Exception) -> HTTPException:
    return HTTPException(status_code=503, detail=str(exc))


@router.get("/health", response_model=HealthResponse, tags=["system"])
def health(store=Depends(get_store), agent=Depends(get_agent)) -> HealthResponse:
    return HealthResponse(
        status="ok",
        vector_store_ready=documents.vector_store_ready(store),
        agent_ready=not isinstance(agent, NotConfiguredAgent),
    )


@router.get("/sources", response_model=list[SourceInfo], tags=["sources"])
def list_sources(store=Depends(get_store)) -> list[SourceInfo]:
    return documents.list_sources(store)


@router.post("/sources/ingest", response_model=IngestResponse, tags=["sources"])
def ingest(body: IngestRequest, llm=Depends(get_llm), store=Depends(get_store)) -> IngestResponse:
    try:
        return documents.ingest_sources(body.sources, llm, store)
    except (MissingAPIKeyError, LLMUnavailableError) as exc:
        raise _llm_unavailable(exc)


@router.post("/search", response_model=SearchResponse, tags=["retrieval"])
def search(body: SearchRequest, llm=Depends(get_llm), store=Depends(get_store)) -> SearchResponse:
    try:
        return documents.search_documents(body.question, body.sources, body.k, llm, store)
    except (MissingAPIKeyError, LLMUnavailableError) as exc:
        raise _llm_unavailable(exc)


@router.post("/ask", response_model=AskResponse, tags=["answers"])
def ask(body: AskRequest, agent=Depends(get_agent), conn=Depends(get_db)) -> AskResponse:
    try:
        return ask_service.ask(body.question, agent, conn, session_id=body.session_id,
                               customer_id=body.customer_id)
    except SessionCustomerMismatchError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except AgentNotConfiguredError as exc:
        raise HTTPException(status_code=501, detail=str(exc))
    except (MissingAPIKeyError, LLMUnavailableError) as exc:
        raise _llm_unavailable(exc)


@router.get("/queries", response_model=list[QueryRecord], tags=["query log"])
def recent_queries(limit: int = Query(default=20, ge=1, le=200), conn=Depends(get_db)) -> list[QueryRecord]:
    return ask_service.recent_queries(conn, limit)


@router.get("/queries/{query_id}", response_model=QueryRecord, tags=["query log"])
def get_query(query_id: int, conn=Depends(get_db)) -> QueryRecord:
    try:
        return ask_service.get_query(conn, query_id)
    except ask_service.QueryNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/queries/{query_id}/feedback", response_model=QueryRecord, tags=["query log"])
def feedback(query_id: int, body: FeedbackRequest, conn=Depends(get_db)) -> QueryRecord:
    try:
        return ask_service.add_feedback(conn, query_id, body)
    except ask_service.QueryNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


def _customer(body: CustomerRequest | None) -> str:
    return (body or CustomerRequest()).customer_id


@router.get("/sessions", response_model=list[SessionSummary], tags=["sessions"])
def list_sessions(customer_id: str = Query(default=DEFAULT_CUSTOMER_ID, pattern=ID_PATTERN),
                  limit: int = Query(default=20, ge=1, le=100), conn=Depends(get_db)) -> list[SessionSummary]:
    return ask_service.list_sessions(conn, customer_id, limit)


@router.post("/sessions/active", response_model=SessionResponse, tags=["sessions"])
def active_session(body: CustomerRequest | None = None, conn=Depends(get_db)) -> SessionResponse:
    """Return the customer's active session (with messages), creating one if there isn't one."""
    return ask_service.active_session(conn, _customer(body))


@router.get("/sessions/{session_id}", response_model=SessionResponse, tags=["sessions"])
def get_session(session_id: str = Path(pattern=ID_PATTERN), conn=Depends(get_db)) -> SessionResponse:
    try:
        return ask_service.get_session(conn, session_id)
    except ask_service.SessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


def _session_action(action, conn, body, session_id) -> SessionResponse:
    try:
        return action(conn, _customer(body), session_id)
    except ask_service.SessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except SessionCustomerMismatchError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.post("/sessions/{session_id}/close", response_model=SessionResponse, tags=["sessions"])
def close_session(session_id: str = Path(pattern=ID_PATTERN), body: CustomerRequest | None = None,
                  conn=Depends(get_db)) -> SessionResponse:
    """End a session; the next question starts a new one."""
    return _session_action(ask_service.close_session, conn, body, session_id)


@router.post("/sessions/{session_id}/resume", response_model=SessionResponse, tags=["sessions"])
def resume_session(session_id: str = Path(pattern=ID_PATTERN), body: CustomerRequest | None = None,
                   conn=Depends(get_db)) -> SessionResponse:
    """Make an earlier session the active one again (closes the current one)."""
    return _session_action(ask_service.resume_session, conn, body, session_id)
