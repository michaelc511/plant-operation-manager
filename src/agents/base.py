"""Contract between the API and the answer agent.

The LangGraph orchestrator in agents/orchestrator.py implements AnswerAgent.
NotConfiguredAgent is a stand-in that makes /ask return 501.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Protocol

Route = Literal["safety", "maintenance", "quality", "out_of_scope"]
Status = Literal["answered", "not_found", "clarify", "out_of_scope"]
Confidence = Literal["high", "medium", "low"]


@dataclass
class AgentResult:
    status: Status
    routes: list[Route]
    answer: str
    # Each citation: source, doc_no, title, section, section_title, page_start, page_end
    citations: list[dict] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)  # uncertainties for the supervisor to check
    confidence: Confidence | None = None
    trace: list[str] = field(default_factory=list)  # orchestration steps, for debugging
    tokens: int = 0
    cost_usd: float = 0.0


class AnswerAgent(Protocol):
    def run(self, question: str) -> AgentResult: ...


class AgentNotConfiguredError(RuntimeError):
    pass


class NotConfiguredAgent:
    def run(self, question: str) -> AgentResult:
        raise AgentNotConfiguredError("The answer agent is not configured. Use /search for retrieval.")
