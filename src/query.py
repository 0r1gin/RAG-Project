import os
import sys
import threading

import anthropic
import chromadb
from dotenv import load_dotenv

from retrieval import N_RESULTS, BM25, Reranker, reciprocal_rank_fusion

load_dotenv(override=True)  # reads ANTHROPIC_API_KEY from .env

MODEL = "claude-sonnet-5-5"   # if you get a model error, check docs.claude.com for current names
N_CANDIDATES = 20             # passages each retriever contributes before fusion
# The cross-encoder costs ~100 ms per 400-word passage on CPU, so only the best few are reranked.
RERANK_CANDIDATES = int(os.getenv("RERANK_CANDIDATES", "10"))

# vector        : embedding similarity only (the original behaviour)
# vector+rerank : vector candidates, reordered by the cross-encoder
# hybrid        : vector + BM25 keyword search, merged with reciprocal rank fusion
# hybrid+rerank : hybrid candidates, reordered by the cross-encoder
RETRIEVAL_MODES = ("vector", "vector+rerank", "hybrid", "hybrid+rerank")
DEFAULT_MODE = os.getenv("RETRIEVAL_MODE", "hybrid+rerank")
if DEFAULT_MODE not in RETRIEVAL_MODES:
    raise RuntimeError(f"RETRIEVAL_MODE must be one of {RETRIEVAL_MODES}, got {DEFAULT_MODE!r}")

active_mode = DEFAULT_MODE   # api.py lowers this to "hybrid" if the reranker can't load

llm = anthropic.Anthropic()
collection = chromadb.PersistentClient(path="chroma_db").get_or_create_collection("docs")
reranker = Reranker()


class KeywordIndex:
    """BM25 over every chunk in the collection. Rebuilt lazily after documents change."""

    def __init__(self, coll):
        self._coll = coll
        self._lock = threading.Lock()
        self._stale = True
        self._ids: list[str] = []
        self._bm25 = BM25([])

    def invalidate(self):
        self._stale = True

    def _ensure_fresh(self):
        with self._lock:
            if self._stale:
                self._stale = False   # set first: a change during the build marks it stale again
                data = self._coll.get(include=["documents"])
                self._ids = data["ids"]
                self._bm25 = BM25(data["documents"] or [])

    def search(self, query: str, top_k: int) -> list[str]:
        self._ensure_fresh()
        return [self._ids[i] for i, _ in self._bm25.search(query, top_k)]


keyword_index = KeywordIndex(collection)


def _vector_ids(question: str, n: int) -> list[str]:
    return collection.query(query_texts=[question], n_results=n, include=[])["ids"][0]


def retrieve(question: str, mode: str | None = None, k: int = N_RESULTS) -> list[dict]:
    """Best k passages for the question as dicts: id, text, source, chunk, score."""
    mode = mode or active_mode
    if mode not in RETRIEVAL_MODES:
        raise ValueError(f"Unknown retrieval mode {mode!r}")
    total = collection.count()
    if total == 0:
        return []
    n = min(N_CANDIDATES, total)

    vector = _vector_ids(question, n)
    if mode.startswith("hybrid"):
        fused = reciprocal_rank_fusion([vector, keyword_index.search(question, n)])
        candidates = [(doc_id, score) for doc_id, score in fused[:n]]
    else:
        candidates = [(doc_id, 1.0 / (rank + 1)) for rank, doc_id in enumerate(vector)]

    ids = [doc_id for doc_id, _ in candidates]
    got = collection.get(ids=ids, include=["documents", "metadatas"])
    by_id = {i: (d, m) for i, d, m in zip(got["ids"], got["documents"], got["metadatas"])}
    passages = [
        {"id": i, "text": by_id[i][0], "source": by_id[i][1]["source"], "chunk": by_id[i][1]["chunk"], "score": s}
        for i, s in candidates if i in by_id
    ]

    if mode.endswith("+rerank") and passages:
        passages = passages[:RERANK_CANDIDATES]
        for p, s in zip(passages, reranker.scores(question, [p["text"] for p in passages])):
            p["score"] = s
        passages.sort(key=lambda p: -p["score"])

    return passages[:k]


def build_prompt(question: str, passages: list[dict]) -> str:
    context = "\n\n".join(
        f"[Source: {p['source']}, chunk {p['chunk']}]\n{p['text']}" for p in passages
    )
    return (
        "Answer the question using ONLY the context below. "
        "If the context doesn't contain the answer, say you don't know. "
        "Mention which source you used.\n\n"
        f"<context>\n{context}\n</context>\n\n"
        f"Question: {question}"
    )


def answer_with_context(question: str, mode: str | None = None) -> dict:
    """Full RAG call. Returns answer, sources and the passages Claude saw (the eval uses these)."""
    passages = retrieve(question, mode)
    response = llm.messages.create(
        model=MODEL,
        max_tokens=1000,
        messages=[{"role": "user", "content": build_prompt(question, passages)}],
    )
    text = "".join(b.text for b in response.content if b.type == "text")
    return {
        "answer": text,
        "sources": sorted({p["source"] for p in passages}),
        "passages": passages,
    }


def answer_with_sources(question: str, mode: str | None = None):
    result = answer_with_context(question, mode)
    return result["answer"], result["sources"]


def answer(question: str, mode: str | None = None) -> str:
    return answer_with_context(question, mode)["answer"]


if __name__ == "__main__":
    q = " ".join(sys.argv[1:]) or input("Question: ")
    print(answer(q))
