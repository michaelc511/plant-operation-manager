"""Run the agent against evaluation/cases.jsonl with the real OpenAI API and score it.

Needs OPENAI_API_KEY in .env and a built vector store (tools/scripts/ingest_docs.py).
Usage from the project root:  python evaluation/run_evals.py [--only CASE_ID ...] [--verbose]

Metrics (targets from README "Success criteria"):
  routing   - every expected source is among the routes (out of scope: routes == ["out_of_scope"])
  status    - answered / not_found / clarify / out_of_scope as expected
  citation  - for answered cases, at least one citation matches an expected (doc, section)
  contains  - the answer includes the expected key values (case-insensitive)
  declines  - out-of-scope and uncovered questions are declined, not answered
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agents.orchestrator import PlantQAAgent  # noqa: E402
from rag.llm import CHAT_MODEL, LLMClient  # noqa: E402
from rag.vector_store import VectorStore  # noqa: E402

CASES = ROOT / "evaluation" / "cases.jsonl"
RESULTS = ROOT / "evaluation" / "results"
TARGETS = {"routing": 0.90, "citation": 0.95, "declines": 0.90}


def score(case: dict, r) -> dict:
    s = {"status": r.status in case["status"]}
    if case["routes"] == ["out_of_scope"]:
        s["routing"] = r.routes == ["out_of_scope"]
    elif case["routes"]:
        s["routing"] = set(case["routes"]) <= set(r.routes)
    if case["sections"] and r.status == "answered":
        got = {(c["doc_no"], c["section"]) for c in r.citations}
        s["citation"] = any(tuple(x) in got for x in case["sections"])
    if case["contains"]:
        s["contains"] = all(x.lower() in r.answer.lower() for x in case["contains"])
    if set(case["status"]) & {"out_of_scope", "not_found"}:
        s["declines"] = r.status != "answered"
    return s


def run_case(agent: PlantQAAgent, case: dict) -> dict:
    t0 = time.perf_counter()
    r = agent.run(case["question"])
    return {
        "id": case["id"], "question": case["question"], "latency_s": round(time.perf_counter() - t0, 2),
        "status": r.status, "routes": r.routes, "confidence": r.confidence, "answer": r.answer,
        "citations": [f"{c['doc_no']} {c['section']}" for c in r.citations], "flags": r.flags,
        "tokens": r.tokens, "cost_usd": r.cost_usd, "scores": score(case, r),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*", help="case ids to run")
    ap.add_argument("--verbose", action="store_true", help="print answers and flags")
    args = ap.parse_args()

    cases = [json.loads(line) for line in CASES.read_text().splitlines() if line.strip()]
    if args.only:
        cases = [c for c in cases if c["id"] in args.only]
    agent = PlantQAAgent(LLMClient(), VectorStore())
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda c: run_case(agent, c), cases))

    print(f"model: {CHAT_MODEL}   cases: {len(results)}\n")
    for res in results:
        fails = [k for k, ok in res["scores"].items() if not ok]
        mark = "PASS" if not fails else "FAIL " + ",".join(fails)
        print(f"{mark:<22} {res['id']:<24} {res['status']:<13} {','.join(res['routes']):<30} "
              f"{'; '.join(res['citations'])[:40]:<40} {res['latency_s']:>5}s")
        if args.verbose or fails:
            print(f"    answer: {res['answer'][:300]!r}")
            for f in res["flags"]:
                print(f"    flag: {f}")

    print("\nmetric      score    target")
    summary = {}
    for metric in ("routing", "status", "citation", "contains", "declines"):
        vals = [r["scores"][metric] for r in results if metric in r["scores"]]
        if vals:
            rate = sum(vals) / len(vals)
            summary[metric] = rate
            tgt = TARGETS.get(metric)
            flag = "" if tgt is None else ("ok" if rate >= tgt else "BELOW TARGET")
            print(f"{metric:<10} {rate:>6.0%} ({sum(vals)}/{len(vals)})  {f'{tgt:.0%}' if tgt else '-':>5} {flag}")
    lat = [r["latency_s"] for r in results]
    cost = sum(r["cost_usd"] for r in results)
    print(f"\nmedian latency {statistics.median(lat):.1f}s (target 5s), max {max(lat):.1f}s")
    print(f"total cost ${cost:.4f}, avg ${cost / len(results):.5f} per question, "
          f"avg {statistics.mean(r['tokens'] for r in results):.0f} tokens")

    RESULTS.mkdir(exist_ok=True)
    out = RESULTS / "latest.json"
    out.write_text(json.dumps({"model": CHAT_MODEL, "summary": summary, "results": results}, indent=2))
    print(f"details: {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
