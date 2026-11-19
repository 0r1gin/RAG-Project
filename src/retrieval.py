"""Retrieval building blocks: BM25 keyword search, rank fusion and cross-encoder reranking.

Kept free of Chroma and Claude so every piece can be unit-tested on its own.
query.py wires these together with the vector index.
"""
import math
import os
import re
import threading
from collections import Counter

N_RESULTS = 3   # passages sent to Claude per question (the eval's hit@3 uses the same number)

# ---------------- tokenizing ----------------
# Letters/digits, keeping trailing # or + so "C#" and "C++" stay distinct from "C".
_TOKEN_RE = re.compile(r"[a-z0-9]+[#+]*")

STOPWORDS = frozenset(
    "a an and are as at be by can do does for from has have how i in is it its of on or "
    "that the their there these this to was were what when where which who why will with "
    "you your".split()
)


def _normalize(token: str) -> str:
    """Very light plural folding, so 'loops' matches 'loop'. Not a full stemmer, on purpose."""
    if len(token) > 4 and token.endswith("ies"):
        return token[:-3] + "y"
    if len(token) > 3 and token.endswith("s") and not token.endswith(("ss", "us", "is")):
        return token[:-1]
    return token


def tokenize(text: str) -> list[str]:
    return [_normalize(t) for t in _TOKEN_RE.findall(text.lower()) if t not in STOPWORDS]


# ---------------- BM25 ----------------
class BM25:
    """Okapi BM25 over a fixed list of documents. Rebuild it when the documents change."""

    def __init__(self, documents: list[str], k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self.doc_terms = [Counter(tokenize(d)) for d in documents]
        self.doc_len = [sum(c.values()) for c in self.doc_terms]
        self.avg_len = (sum(self.doc_len) / len(self.doc_len)) if self.doc_len else 0.0
        df = Counter()
        for terms in self.doc_terms:
            df.update(terms.keys())
        n = len(documents)
        # BM25+ style idf: always positive, so very common terms still count a little.
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def scores(self, query: str) -> list[float]:
        q_terms = [t for t in tokenize(query) if t in self.idf]
        out = []
        for terms, length in zip(self.doc_terms, self.doc_len):
            s = 0.0
            norm = self.k1 * (1 - self.b + self.b * length / self.avg_len) if self.avg_len else self.k1
            for t in q_terms:
                tf = terms.get(t, 0)
                if tf:
                    s += self.idf[t] * tf * (self.k1 + 1) / (tf + norm)
            out.append(s)
        return out

    def search(self, query: str, top_k: int) -> list[tuple[int, float]]:
        """(document index, score) for the best matches. Documents with no matching term are left out."""
        ranked = sorted(
            ((i, s) for i, s in enumerate(self.scores(query)) if s > 0),
            key=lambda pair: (-pair[1], pair[0]),
        )
        return ranked[:top_k]


# ---------------- fusion ----------------
def reciprocal_rank_fusion(rankings: list[list[str]], k: int = 60) -> list[tuple[str, float]]:
    """Merge several ranked id lists. Each id scores sum(1 / (k + rank)) over the lists it appears in.

    Uses ranks only, so BM25 scores and vector distances never need to be on the same scale.
    k=60 is the value from the original RRF paper; larger k flattens the advantage of the top ranks.
    """
    fused: dict[str, float] = {}
    first_seen: dict[str, int] = {}
    for ranking in rankings:
        for rank, doc_id in enumerate(ranking, start=1):
            fused[doc_id] = fused.get(doc_id, 0.0) + 1.0 / (k + rank)
            first_seen.setdefault(doc_id, len(first_seen))
    return sorted(fused.items(), key=lambda pair: (-pair[1], first_seen[pair[0]]))


# ---------------- reranking ----------------
RERANK_MODEL = os.getenv("RERANK_MODEL", "Xenova/ms-marco-MiniLM-L-6-v2")
MODEL_CACHE = os.getenv("FASTEMBED_CACHE_PATH", ".cache/fastembed")


class Reranker:
    """Cross-encoder that scores (question, passage) pairs together. Loaded on first use."""

    def __init__(self, model_name: str = RERANK_MODEL, cache_dir: str = MODEL_CACHE):
        self.model_name, self.cache_dir = model_name, cache_dir
        self._model = None
        self._lock = threading.Lock()

    def load(self):
        with self._lock:
            if self._model is None:
                from fastembed.rerank.cross_encoder import TextCrossEncoder   # heavy import, only when needed
                self._model = TextCrossEncoder(model_name=self.model_name, cache_dir=self.cache_dir)
        return self._model

    def scores(self, query: str, passages: list[str]) -> list[float]:
        if not passages:
            return []
        return [float(s) for s in self.load().rerank(query, passages)]
