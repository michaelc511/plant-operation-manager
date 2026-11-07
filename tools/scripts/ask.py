"""Ask the plant documentation agents a question from the command line (no server needed).

Runs the LangGraph orchestrator (router -> retrieval -> verifier) against the local Chroma
vector store. Needs OPENAI_API_KEY in .env and a built vector store (tools/scripts/ingest_docs.py).

Usage (from the project root, venv active):
  python tools/scripts/ask.py "How often do we grease the CV-3 bearings?"   # one question
  python tools/scripts/ask.py                                               # interactive mode
  python tools/scripts/ask.py --trace "..."                                 # show agent steps and evidence
  python tools/scripts/ask.py --json "..."                                  # raw JSON result
"""

from __future__ import annotations

import argparse
import json
import sys
import textwrap
import time
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from agents.orchestrator import PlantQAAgent  # noqa: E402
from rag.config import SOURCES  # noqa: E402
from rag.llm import CHAT_MODEL, LLMClient, LLMUnavailableError, MissingAPIKeyError  # noqa: E402
from rag.vector_store import VectorStore  # noqa: E402

BOLD, DIM, RED, YEL, GRN, RST = "\033[1m", "\033[2m", "\033[31m", "\033[33m", "\033[32m", "\033[0m"
STATUS_COLOR = {"answered": GRN, "not_found": YEL, "clarify": YEL, "out_of_scope": DIM}


def color(on: bool):
    return (lambda c, s: f"{c}{s}{RST}") if on else (lambda c, s: s)


def print_result(r, seconds: float, show_trace: bool, use_color: bool) -> None:
    c = color(use_color)
    conf = f" | confidence {r.confidence}" if r.confidence else ""
    print(c(STATUS_COLOR.get(r.status, ""), f"\n{r.status.upper()}") + f" | routes: {', '.join(r.routes) or '-'}{conf}\n")
    for para in r.answer.split("\n"):
        print(textwrap.fill(para, width=100) if para else "")
    if r.citations:
        print(c(BOLD, "\nSources"))
        for i, ci in enumerate(r.citations, 1):
            pages = f"p.{ci['page_start']}" + (f"-{ci['page_end']}" if ci["page_end"] != ci["page_start"] else "")
            print(f"  [{i}] {ci['doc_no']} {ci['title']}, section {ci['section']} {ci['section_title']} ({pages})")
    if r.flags:
        print(c(YEL, "\nCheck before acting"))
        for f in r.flags:
            print(c(YEL, textwrap.fill(f, width=100, initial_indent="  ! ", subsequent_indent="    ")))
    if show_trace:
        print(c(DIM, "\nAgent steps"))
        for t in r.trace:
            print(c(DIM, f"  - {t}"))
    print(c(DIM, f"\n{r.tokens} tokens | ${r.cost_usd:.4f} | {seconds:.1f}s | {CHAT_MODEL}"))


def ask(agent: PlantQAAgent, question: str, args, use_color: bool) -> bool:
    question = " ".join(question.split())
    if len(question) < 3:
        print("Please ask a longer question.")
        return True
    t0 = time.perf_counter()
    try:
        r = agent.run(question)
    except (MissingAPIKeyError, LLMUnavailableError) as exc:
        print(color(use_color)(RED, f"error: {exc}"), file=sys.stderr)
        return False
    if args.json:
        print(json.dumps(asdict(r), indent=2))
    else:
        print_result(r, time.perf_counter() - t0, args.trace, use_color)
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description="Ask the plant documentation agents a question.")
    ap.add_argument("question", nargs="*", help="question to ask; omit for interactive mode")
    ap.add_argument("--trace", action="store_true", help="show the orchestrator and subagent steps")
    ap.add_argument("--json", action="store_true", help="print the raw result as JSON")
    ap.add_argument("--no-color", action="store_true")
    args = ap.parse_args()
    use_color = sys.stdout.isatty() and not args.no_color and not args.json

    store = VectorStore()
    empty = [k for k in SOURCES if store.count(k) == 0]
    if empty:
        print(f"error: vector store has no chunks for {', '.join(empty)}. "
              "Build it first: python tools/scripts/ingest_docs.py", file=sys.stderr)
        return 1
    agent = PlantQAAgent(LLMClient(), store)

    if args.question:
        return 0 if ask(agent, " ".join(args.question), args, use_color) else 1

    c = color(use_color)
    print(c(BOLD, "Plant documentation assistant") + " - safety, maintenance and quality documents.")
    print("Type a question and press Enter. Commands: :trace (toggle agent steps), :quit\n")
    while True:
        try:
            q = input(c(BOLD, "question> ")).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not q:
            continue
        if q in (":q", ":quit", "exit", "quit"):
            return 0
        if q == ":trace":
            args.trace = not args.trace
            print(f"agent steps {'on' if args.trace else 'off'}")
            continue
        ask(agent, q, args, use_color)
        print()


if __name__ == "__main__":
    sys.exit(main())
