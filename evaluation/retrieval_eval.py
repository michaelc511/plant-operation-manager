"""Compare retrieval modes (vector-only vs hybrid) on evaluation/retrieval_cases.jsonl.

Mirrors the retrieval agent: search each listed source (top 4 each, vector min score 0.30),
merge, keep the best 8 passages. A case is a hit when any expected (doc, section) is kept.
Needs OPENAI_API_KEY (embeddings only, a fraction of a cent) and a built vector store.

Usage from the project root:  python evaluation/retrieval_eval.py [--verbose]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agents.retrieval import K_PER_SOURCE, MAX_EVIDENCE, MIN_SCORE  # noqa: E402
from rag.hybrid import HybridSearcher  # noqa: E402
from rag.llm import LLMClient  # noqa: E402
from rag.vector_store import VectorStore  # noqa: E402

CASES = ROOT / "evaluation" / "retrieval_cases.jsonl"


def retrieve(searcher, case, vector):
    hits = [h for s in case["sources"] for h in searcher.search(s, case["question"], vector, K_PER_SOURCE, MIN_SCORE)]
    hits.sort(key=lambda h: h.score, reverse=True)
    return hits[:MAX_EVIDENCE]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    cases = [json.loads(line) for line in CASES.read_text().splitlines() if line.strip()]
    llm, store = LLMClient(), VectorStore()
    emb = llm.embed([c["question"] for c in cases])
    searchers = {m: HybridSearcher(store, mode=m) for m in ("vector", "hybrid")}

    stats = {m: {"hit": 0, "top1": 0, "rr": 0.0} for m in searchers}
    by_group = {m: {"natural": [0, 0], "id": [0, 0]} for m in searchers}
    print(f"{'case':<20} {'vector':<16} {'hybrid':<16}")
    for case, vector in zip(cases, emb.vectors):
        expected = {tuple(x) for x in case["expected"]}
        row = []
        for mode, searcher in searchers.items():
            hits = retrieve(searcher, case, vector)
            keys = [(h.metadata["doc_no"], h.metadata["section"]) for h in hits]
            rank = next((i for i, k in enumerate(keys, 1) if k in expected), None)
            group = "id" if case["id"].startswith("id-") else "natural"
            by_group[mode][group][1] += 1
            if rank:
                stats[mode]["hit"] += 1
                stats[mode]["rr"] += 1 / rank
                stats[mode]["top1"] += rank == 1
                by_group[mode][group][0] += 1
            row.append(f"rank {rank}" if rank else "MISS")
            if args.verbose:
                row[-1] += " [" + ", ".join(f"{d} {s}" for d, s in keys[:3]) + "]"
        print(f"{case['id']:<20} {row[0]:<16} {row[1]:<16}")

    n = len(cases)
    print(f"\n{'metric':<26} {'vector':>8} {'hybrid':>8}")
    for label, key in (("hit rate (in top 8)", "hit"), ("top-1 accuracy", "top1")):
        print(f"{label:<26} {stats['vector'][key] / n:>8.0%} {stats['hybrid'][key] / n:>8.0%}")
    print(f"{'MRR':<26} {stats['vector']['rr'] / n:>8.3f} {stats['hybrid']['rr'] / n:>8.3f}")
    for group in ("natural", "id"):
        v, h = by_group["vector"][group], by_group["hybrid"][group]
        print(f"{'hit rate, ' + group + ' questions':<26} {v[0]}/{v[1]:<6} {h[0]}/{h[1]:<6}")
    print(f"\nembedding cost ${emb.cost_usd:.5f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
