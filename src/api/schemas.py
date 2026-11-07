"""Request and response models for the HTTP API."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

SourceKey = Literal["safety", "maintenance", "quality"]
RouteKey = Literal["safety", "maintenance", "quality", "out_of_scope"]
AnswerStatus = Literal["answered", "not_found", "clarify", "out_of_scope"]
Confidence = Literal["high", "medium", "low"]

# Opaque identifiers only (no names or emails): letters, digits, "_" and "-".
ID_PATTERN = r"^[A-Za-z0-9_-]{1,64}$"
DEFAULT_CUSTOMER_ID = "1"


class _Question(BaseModel):
    question: str = Field(min_length=3, max_length=1000)

    @field_validator("question")
    @classmethod
    def strip_question(cls, v: str) -> str:
        v = " ".join(v.split())
        if len(v) < 3:
            raise ValueError("question is too short")
        return v


class Citation(BaseModel):
    source: SourceKey
    doc_no: str
    title: str
    section: str
    section_title: str
    page_start: int
    page_end: int


# ---- health
class HealthResponse(BaseModel):
    status: Literal["ok"]
    vector_store_ready: bool
    agent_ready: bool


# ---- sources
class SourceInfo(BaseModel):
    key: SourceKey
    doc_no: str
    title: str
    filename: str
    chunks: int


class IngestRequest(BaseModel):
    sources: list[SourceKey] | None = Field(default=None, description="Sources to re-index; all if omitted")


class IngestResult(BaseModel):
    source: SourceKey
    chunks: int
    tokens: int
    cost_usd: float
    latency_s: float


class IngestResponse(BaseModel):
    results: list[IngestResult]
    total_cost_usd: float


# ---- search (retrieval only, no LLM answer)
class SearchRequest(_Question):
    sources: list[SourceKey] | None = Field(default=None, description="Sources to search; all if omitted")
    k: int = Field(default=4, ge=1, le=10, description="Results per source")


class SearchHit(BaseModel):
    text: str
    score: float = Field(description="Fused hybrid score, 0-1 (1 = ranked first by both retrievers)")
    matched_by: Literal["vector", "keyword", "both"] = "vector"
    vector_score: float | None = Field(default=None, description="Cosine similarity, if found by vector search")
    keyword_score: float | None = Field(default=None, description="BM25 score, if found by keyword search")
    citation: Citation


class SearchResponse(BaseModel):
    question: str
    hits: list[SearchHit]


# ---- ask (answer agent)
class AskRequest(_Question):
    session_id: str | None = Field(default=None, pattern=ID_PATTERN,
                                   description="Conversation to append to; a new one is started if omitted")
    customer_id: str = Field(default=DEFAULT_CUSTOMER_ID, pattern=ID_PATTERN,
                             description="Opaque customer ID; never a name or email")


class Usage(BaseModel):
    tokens: int = 0
    cost_usd: float = 0.0


class AskResponse(BaseModel):
    query_id: int
    question: str
    status: AnswerStatus
    routes: list[RouteKey]
    answer: str
    citations: list[Citation]
    flags: list[str] = Field(description="Uncertainties the supervisor should double-check")
    confidence: Confidence | None
    trace: list[str] = Field(description="Orchestrator and subagent steps, for debugging")
    usage: Usage
    latency_ms: int
    session_id: str
    customer_id: str


# ---- query log and feedback
class FeedbackRequest(BaseModel):
    helpful: bool
    note: str | None = Field(default=None, max_length=1000)


class QueryRecord(BaseModel):
    id: int
    created_at: str
    question: str
    status: AnswerStatus
    routes: list[RouteKey]
    answer: str
    citations: list[Citation]
    flags: list[str]
    confidence: Confidence | None
    trace: list[str]
    usage: Usage
    latency_ms: int
    helpful: bool | None
    feedback_note: str | None


# ---- customer sessions
class SessionMessage(BaseModel):
    id: int
    session_id: str
    customer_id: str
    role: Literal["user", "assistant"]
    message: str | None = Field(description="The question (user turns)")
    answer: str | None = Field(description="The answer (assistant turns)")
    citations: list[Citation]
    confidence: Confidence | None
    status: AnswerStatus
    query_id: int | None
    created_at: str


class SessionResponse(BaseModel):
    session_id: str
    customer_id: str
    status: Literal["active", "closed"]
    created_at: str
    last_active_at: str
    created: bool = Field(default=False, description="True if this call started a new session")
    messages: list[SessionMessage]


class CustomerRequest(BaseModel):
    customer_id: str = Field(default=DEFAULT_CUSTOMER_ID, pattern=ID_PATTERN)


class SessionSummary(BaseModel):
    session_id: str
    customer_id: str
    status: Literal["active", "closed"]
    created_at: str
    last_active_at: str
    question_count: int
    first_question: str | None
