"""Orchestrator: a LangGraph supervisor that runs the router, retrieval and verifier subagents.

    START -> orchestrator --(next)--> router    -> orchestrator
                          --(next)--> retrieval -> orchestrator
                          --(next)--> verifier  -> orchestrator
                          --(next)--> END

The orchestrator's decisions are plain code (no LLM call), so they are cheap and testable:
  - out of scope / needs clarification  -> finish without retrieval
  - no evidence in the routed sources   -> widen the search to all sources once
  - verifier finds no answer            -> widen to all sources once and verify again
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from agents.base import AgentResult
from agents.retrieval import RetrievalAgent
from agents.router import RouterAgent
from agents.state import SOURCE_ORDER, GraphState
from agents.verifier import VerifierAgent
from rag.llm import LLMClient
from rag.vector_store import VectorStore

OUT_OF_SCOPE_TEXT = (
    "That question is outside the plant documentation I can search (safety procedures, "
    "maintenance manuals and quality control standards). Please ask your supervisor or the right department."
)
NO_EVIDENCE_TEXT = "I couldn't find this in the plant documentation."


def _finish(state: GraphState, **result) -> dict:
    final = {"routes": state.get("searched_sources") or state.get("search_sources", []), "citations": [],
             "flags": [], "confidence": None, **result}
    return {"next": "end", "final": final, "trace": [f"orchestrator: finish ({final['status']})"]}


def _widen(state: GraphState, reason: str) -> dict:
    return {
        "next": "retrieval",
        "expanded": True,
        "search_sources": [s for s in SOURCE_ORDER if s not in state.get("searched_sources", [])],
        "verification": None,
        "trace": [f"orchestrator: {reason}; widening search to all sources"],
    }


def orchestrate(state: GraphState) -> dict:
    router = state.get("router")
    if router is None:
        return {"next": "router", "trace": ["orchestrator: -> router"]}

    if router["category"] == "out_of_scope":
        return _finish(state, status="out_of_scope", routes=["out_of_scope"], answer=OUT_OF_SCOPE_TEXT)
    if router["category"] == "clarify":
        return _finish(state, status="clarify", routes=[],
                       answer=router["clarifying_question"] or "Could you give more detail (machine, part or task)?")

    can_widen = not state.get("expanded") and len(state.get("searched_sources", [])) < len(SOURCE_ORDER)

    if not state.get("retrieval_done"):
        return {"next": "retrieval", "trace": [f"orchestrator: -> retrieval {state['search_sources']}"]}

    if not state.get("evidence"):
        if can_widen:
            return _widen(state, "no relevant passages")
        return _finish(state, status="not_found", answer=NO_EVIDENCE_TEXT, confidence="low",
                       flags=["No relevant passages were found in any source."])

    v = state.get("verification")
    if not v:
        return {"next": "verifier", "trace": ["orchestrator: -> verifier"]}

    if v["status"] == "not_found" and can_widen:
        return _widen(state, "verifier found no answer")

    flags = list(v["flags"])
    if state.get("expanded"):
        flags.append("The router's first choice of source had no answer; other sources were searched too.")
    return _finish(state, status=v["status"], answer=v["answer"], citations=v["citations"],
                   flags=flags, confidence=v["confidence"])


def build_graph(llm: LLMClient, store: VectorStore):
    g = StateGraph(GraphState)
    g.add_node("orchestrator", orchestrate)
    g.add_node("router", RouterAgent(llm))
    g.add_node("retrieval", RetrievalAgent(llm, store))
    g.add_node("verifier", VerifierAgent(llm))
    g.add_edge(START, "orchestrator")
    g.add_conditional_edges("orchestrator", lambda s: s["next"],
                            {"router": "router", "retrieval": "retrieval", "verifier": "verifier", "end": END})
    for sub in ("router", "retrieval", "verifier"):
        g.add_edge(sub, "orchestrator")
    return g.compile()


class PlantQAAgent:
    """AnswerAgent implementation backed by the LangGraph orchestrator."""

    def __init__(self, llm: LLMClient, store: VectorStore):
        self.graph = build_graph(llm, store)

    def run(self, question: str) -> AgentResult:
        state = self.graph.invoke({"question": question, "trace": [], "tokens": 0, "cost_usd": 0.0},
                                  {"recursion_limit": 20})
        f = state["final"]
        return AgentResult(
            status=f["status"], routes=f["routes"], answer=f["answer"], citations=f["citations"],
            flags=f["flags"], confidence=f["confidence"], trace=state["trace"],
            tokens=state["tokens"], cost_usd=round(state["cost_usd"], 6),
        )
