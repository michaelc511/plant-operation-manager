"""BM25 keyword index over chunk text. Catches exact IDs (HP-400, DS-3C, EHS-F-07, A-102) and
specific terms that embeddings can rank poorly."""

from __future__ import annotations

import math
import re
from collections import Counter

# Words joined by - . / stay one token ("hp-400", "3.1", "ehs-f-07"); their parts are indexed too.
_TOKEN = re.compile(r"[a-z0-9]+(?:[-./][a-z0-9]+)*")
_SPLIT = re.compile(r"[-./]")
_STOP = frozenset(
    "a an and are as at be by can do does for from has have how i if in is it its me must my of on or "
    "our should so that the their them then there these this to was we what when where which who why "
    "will with you your".split()
)


def _stem(t: str) -> str:
    # Light plural folding only: bearings -> bearing, gloves -> glove. Leaves IDs and numbers alone.
    if len(t) > 4 and t.isalpha() and t.endswith("s") and not t.endswith("ss"):
        return t[:-1]
    return t


def tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    for tok in _TOKEN.findall(text.lower()):
        if tok in _STOP:
            continue
        tokens.append(_stem(tok))
        if _SPLIT.search(tok):
            tokens += [_stem(p) for p in _SPLIT.split(tok) if p and p not in _STOP]
    return tokens


class BM25Index:
    def __init__(self, ids: list[str], documents: list[str], k1: float = 1.5, b: float = 0.75):
        self.ids = ids
        self.k1, self.b = k1, b
        self.doc_tf = [Counter(tokenize(d)) for d in documents]
        self.doc_len = [sum(tf.values()) for tf in self.doc_tf]
        self.avg_len = (sum(self.doc_len) / len(self.doc_len)) if self.doc_len else 0.0
        df: Counter = Counter()
        for tf in self.doc_tf:
            df.update(tf.keys())
        n = len(documents)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def search(self, query: str, k: int) -> list[tuple[str, float]]:
        """Top-k (id, score) with score > 0, best first."""
        terms = [t for t in dict.fromkeys(tokenize(query)) if t in self.idf]
        if not terms or not self.ids:
            return []
        scores = []
        for i, tf in enumerate(self.doc_tf):
            s = 0.0
            norm = self.k1 * (1 - self.b + self.b * self.doc_len[i] / (self.avg_len or 1))
            for t in terms:
                f = tf.get(t)
                if f:
                    s += self.idf[t] * f * (self.k1 + 1) / (f + norm)
            if s > 0:
                scores.append((self.ids[i], s))
        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:k]
