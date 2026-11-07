"""Subagent 1: Router. Classifies the question to safety / maintenance / quality, out of scope, or clarify."""

from __future__ import annotations

from agents.prompts import load_prompt
from agents.state import SOURCE_ORDER, GraphState, RouterOutput
from rag.llm import LLMClient

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["category", "sources", "safety_relevant", "clarifying_question", "reasoning"],
    "properties": {
        "category": {"type": "string", "enum": ["in_scope", "out_of_scope", "clarify"]},
        "sources": {"type": "array", "items": {"type": "string", "enum": SOURCE_ORDER}},
        "safety_relevant": {"type": "boolean"},
        "clarifying_question": {"type": "string"},
        "reasoning": {"type": "string"},
    },
}


class RouterAgent:
    name = "router"

    def __init__(self, llm: LLMClient):
        self.llm = llm

    def __call__(self, state: GraphState) -> dict:
        res = self.llm.chat_json(load_prompt("router"), f"Question: {state['question']}", "route", SCHEMA)
        out: RouterOutput = res.data
        sources = set(out["sources"]) & set(SOURCE_ORDER)
        if out["category"] == "in_scope":
            if out["safety_relevant"]:
                sources.add("safety")  # FR5: always bring in safety guidance when relevant
            if not sources:
                sources = set(SOURCE_ORDER)  # router unsure which: search everything
        else:
            sources = set()
        out = {**out, "sources": [s for s in SOURCE_ORDER if s in sources]}
        return {
            "router": out,
            "search_sources": out["sources"],
            "trace": [f"router: {out['category']} -> {out['sources'] or '-'} (safety_relevant={out['safety_relevant']})"],
            "tokens": res.total_tokens,
            "cost_usd": res.cost_usd,
        }
