"""Embed the source PDFs into the local vector store, or run a test search against it.

Usage (from the project root, with the venv active and OPENAI_API_KEY in .env):
  python tools/scripts/ingest_docs.py                       # re-index all sources
  python tools/scripts/ingest_docs.py --source safety       # re-index one source
  python tools/scripts/ingest_docs.py --search "How often do we grease the CV-3 bearings?"
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from rag.config import SOURCES  # noqa: E402
from rag.ingest import ingest, search  # noqa: E402
from rag.llm import EMBEDDING_MODEL, MissingAPIKeyError  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", action="append", choices=list(SOURCES), help="limit to this source (repeatable)")
    ap.add_argument("--search", help="run a test query instead of ingesting")
    ap.add_argument("-k", type=int, default=3)
    args = ap.parse_args()
    try:
        if args.search:
            for h in search(args.search, args.source, args.k):
                m = h["metadata"]
                vec = "-" if h["vector_score"] is None else f"{h['vector_score']:.2f}"
                kw = "-" if h["keyword_score"] is None else f"{h['keyword_score']:.1f}"
                print(f"{h['score']:.3f}  {h['matched_by']:<7} (vec {vec:>4}, bm25 {kw:>4})  "
                      f"{m['doc_no']} s{m['section']} {m['section_title']} (p{m['page_start']})")
            return 0
        reports = ingest(args.source)
    except MissingAPIKeyError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    print(f"model: {EMBEDDING_MODEL}")
    for r in reports:
        print(f"{r.source:<12} {r.chunks:>3} chunks  {r.tokens:>6} tokens  ${r.cost_usd:.5f}  {r.latency_s:.1f}s")
    print(f"total cost: ${sum(r.cost_usd for r in reports):.5f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
