"""Unit tests for the retrieval building blocks. No network, Chroma or Claude needed."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from retrieval import BM25, reciprocal_rank_fusion, tokenize  # noqa: E402


# ---------------- tokenize ----------------
def test_tokenize_lowercases_and_drops_stopwords():
    assert tokenize("What are the Two kinds of LOOPS?") == ["two", "kind", "loop"]


def test_tokenize_keeps_language_names_distinct():
    assert tokenize("C, C# and C++") == ["c", "c#", "c++"]


@pytest.mark.parametrize("word, expected", [
    ("loops", "loop"), ("statements", "statement"), ("libraries", "library"),
    ("class", "class"), ("status", "status"), ("analysis", "analysis"), ("cpu", "cpu"),
])
def test_tokenize_folds_simple_plurals_only(word, expected):
    assert tokenize(word) == [expected]


# ---------------- BM25 ----------------
DOCS = [
    "Definite loops repeat a known number of times; indefinite loops repeat until a condition.",
    "The CPU is the main processor of a computer.",
    "Assembly language uses mnemonics instead of binary machine code.",
    "Decision structures decide whether statements are executed.",
]


def test_bm25_ranks_the_matching_document_first():
    bm25 = BM25(DOCS)
    assert bm25.search("what does assembly language use", top_k=3)[0][0] == 2
    assert bm25.search("main processor", top_k=3)[0][0] == 1


def test_bm25_matches_plural_query_against_singular_text():
    bm25 = BM25(["A loop repeats code.", "Variables store values."])
    assert bm25.search("loops", top_k=2)[0][0] == 0


def test_bm25_leaves_out_documents_with_no_matching_term():
    results = BM25(DOCS).search("mnemonics", top_k=10)
    assert [i for i, _ in results] == [2]


def test_bm25_respects_top_k_and_sorts_descending():
    results = BM25(DOCS).search("loops computer statements language", top_k=2)
    assert len(results) == 2
    assert results[0][1] >= results[1][1]


def test_bm25_rare_terms_outweigh_common_ones():
    docs = ["computer " * 3 + "cache", "computer memory", "computer disk", "computer screen"]
    # "cache" appears in one document, "computer" in all of them.
    assert BM25(docs).search("computer cache", top_k=1)[0][0] == 0


def test_bm25_handles_empty_corpus_and_unknown_terms():
    assert BM25([]).search("anything", top_k=5) == []
    assert BM25(DOCS).search("zebra", top_k=5) == []


# ---------------- reciprocal rank fusion ----------------
def test_rrf_rewards_documents_found_by_both_retrievers():
    vector = ["a", "b", "c"]
    keyword = ["c", "d", "a"]
    fused = [doc_id for doc_id, _ in reciprocal_rank_fusion([vector, keyword])]
    assert fused[:2] == ["a", "c"]       # in both lists
    assert set(fused) == {"a", "b", "c", "d"}


def test_rrf_scores_match_the_formula():
    fused = dict(reciprocal_rank_fusion([["x", "y"], ["y"]], k=60))
    assert fused["x"] == pytest.approx(1 / 61)
    assert fused["y"] == pytest.approx(1 / 62 + 1 / 61)


def test_rrf_breaks_ties_by_first_appearance():
    fused = [doc_id for doc_id, _ in reciprocal_rank_fusion([["a", "b"], ["b", "a"]])]
    assert fused == ["a", "b"]


def test_rrf_with_one_list_keeps_its_order():
    order = ["q", "w", "e"]
    assert [d for d, _ in reciprocal_rank_fusion([order])] == order


def test_rrf_with_no_lists_is_empty():
    assert reciprocal_rank_fusion([]) == []
