"""Subagent 3: Response verification.

An LLM drafts the answer from the evidence only and breaks it into claims. Code then checks it:
every citation must point to retrieved evidence, unsupported claims are flagged, an answer
without valid citations is downgraded to not_found, and a safety-relevant question with no
safety citation is flagged.
"""

from __future__ import annotations

import re

from agents.prompts import load_prompt
from agents.state import GraphState, Verification
from rag.llm import LLMClient

CITATION_FIELDS = ("source", "doc_no", "title", "section", "section_title", "page_start", "page_end")
_MARKER = re.compile(r"\[(E\d+)\]")
NOT_FOUND_TEXT = "I couldn't find this in the plant documentation."

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["status", "answer", "claims", "uncertainties", "follow_up_question", "confidence"],
    "properties": {
        "status": {"type": "string", "enum": ["answered", "not_found", "clarify"]},
        "answer": {"type": "string"},
        "claims": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["claim", "evidence_ids", "supported"],
                "properties": {
                    "claim": {"type": "string"},
                    "evidence_ids": {"type": "array", "items": {"type": "string"}},
                    "supported": {"type": "boolean"},
                },
            },
        },
        "uncertainties": {"type": "array", "items": {"type": "string"}},
        "follow_up_question": {"type": "string"},
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
    },
}


def _format_evidence(evidence) -> str:
    blocks = []
    for e in evidence:
        m = e["metadata"]
        text = e["text"].replace("</evidence>", "")
        blocks.append(
            f'<evidence id="{e["id"]}" doc="{m["doc_no"]}" section="{m["section"]} {m["section_title"]}" '
            f'pages="{m["page_start"]}-{m["page_end"]}">\n{text}\n</evidence>'
        )
    return "\n\n".join(blocks)


def check(draft: dict, evidence: list, safety_relevant: bool) -> Verification:
    """Deterministic verification of the LLM draft against the retrieved evidence."""
    by_id = {e["id"]: e for e in evidence}
    flags = list(draft["uncertainties"])
    confidence = draft["confidence"]
    status = draft["status"]
    answer = draft["answer"].strip()

    # 1. Citations come from inline [E#] markers plus the evidence behind supported claims,
    #    and must refer to evidence we actually retrieved.
    inline = _MARKER.findall(answer)
    claim_ids = [i for c in draft["claims"] if c["supported"] for i in c["evidence_ids"]]
    cited = list(dict.fromkeys(inline + claim_ids))
    bad = [c for c in cited if c not in by_id]
    if bad:
        flags.append(f"Removed citations to passages that were not retrieved: {', '.join(bad)}.")
        confidence = "low"
    valid = [c for c in cited if c in by_id]

    # 2. Unsupported claims.
    for claim in draft["claims"]:
        ids = [i for i in claim["evidence_ids"] if i in by_id]
        if not claim["supported"] or not ids:
            flags.append(f"Not confirmed by the documents: {claim['claim']}")
            confidence = "low"

    # 3. An answer must be grounded in at least one valid citation (FR3).
    if status == "answered" and not valid:
        flags.append("The draft answer had no valid citations, so it was withheld.")
        status, answer, confidence = "not_found", NOT_FOUND_TEXT, "low"

    # One citation per distinct (doc, section, pages); two chunks of one section share a number.
    citations: list[dict] = []
    number: dict[str, int] = {}
    for eid in valid:
        c = {k: by_id[eid]["metadata"][k] for k in CITATION_FIELDS}
        if c not in citations:
            citations.append(c)
        number[eid] = citations.index(c) + 1

    # Renumber markers [E3] -> [1] in citation order; drop invalid markers and repeats like [1][1].
    answer = _MARKER.sub(lambda m: f"[{number[m.group(1)]}]" if m.group(1) in number else "", answer)
    answer = re.sub(r"(\[\d+\])(?:\1)+", r"\1", answer).strip()
    if status != "not_found" and valid and not any(m in by_id for m in inline):
        answer += " " + "".join(f"[{n}]" for n in dict.fromkeys(number.values()))  # model left out markers

    # 4. FR5: safety-relevant work should cite a safety procedure.
    if safety_relevant and status == "answered" and not any(c["source"] == "safety" for c in citations):
        flags.append("This task has safety implications, but no safety procedure was cited. "
                     "Check EHS-SOP-001 (lockout and PPE) before starting.")
        if confidence == "high":
            confidence = "medium"

    if status == "clarify" and draft["follow_up_question"]:
        answer = f"{answer}\n\n{draft['follow_up_question']}".strip()

    return Verification(status=status, answer=answer, citations=citations,
                        flags=list(dict.fromkeys(flags)), confidence=confidence)


class VerifierAgent:
    name = "verifier"

    def __init__(self, llm: LLMClient):
        self.llm = llm

    def __call__(self, state: GraphState) -> dict:
        evidence = state.get("evidence", [])
        user = f"Question: {state['question']}\n\nEvidence:\n{_format_evidence(evidence)}"
        res = self.llm.chat_json(load_prompt("verifier"), user, "verified_answer", SCHEMA)
        result = check(res.data, evidence, state["router"]["safety_relevant"])
        return {
            "verification": result,
            "trace": [f"verifier: {result['status']}, {len(result['citations'])} citations, "
                      f"{len(result['flags'])} flags, confidence {result['confidence']}"],
            "tokens": res.total_tokens,
            "cost_usd": res.cost_usd,
        }
