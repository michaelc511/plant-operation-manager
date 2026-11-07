"""Shared LangGraph state passed between the orchestrator and its subagents."""

from __future__ import annotations

import operator
from typing import Annotated, Literal, TypedDict

SOURCE_ORDER = ["safety", "maintenance", "quality"]


class Evidence(TypedDict):
    id: str  # "E1", "E2", ...
    text: str
    score: float
    metadata: dict  # source, doc_no, title, section, section_title, page_start, page_end


class RouterOutput(TypedDict):
    category: Literal["in_scope", "out_of_scope", "clarify"]
    sources: list[str]
    safety_relevant: bool
    clarifying_question: str
    reasoning: str


class Verification(TypedDict):
    status: Literal["answered", "not_found", "clarify"]
    answer: str
    citations: list[dict]
    flags: list[str]
    confidence: Literal["high", "medium", "low"]


class GraphState(TypedDict, total=False):
    question: str
    next: str  # orchestrator's routing decision
    router: RouterOutput
    search_sources: list[str]  # sources the retrieval agent should search
    searched_sources: list[str]  # sources already searched
    expanded: bool  # retrieval was widened to all sources
    evidence: list[Evidence]
    retrieval_done: bool
    verification: Verification
    final: dict  # AgentResult fields, set by the orchestrator when finished
    trace: Annotated[list[str], operator.add]
    tokens: Annotated[int, operator.add]
    cost_usd: Annotated[float, operator.add]
