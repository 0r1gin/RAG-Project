"""Unit tests for the evaluation logic. No network, Chroma or Claude needed."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import evaluation as ev  # noqa: E402


# ---------------- keyword matching ----------------
def test_terms_match_whole_words_only():
    assert ev.term_in("Uses the CPU.", "cpu")
    assert not ev.term_in("Java and JavaScript", "javas")
    assert ev.term_in("C# is used", "C#")


def test_synonyms_any_one_counts():
    assert ev.match_keyword("It has two kinds", ["2", "two"]) == "two"
    assert ev.match_keyword("nothing here", ["2", "two"]) is None


def test_match_all_needs_every_keyword():
    ok, found, missing = ev.check_keywords("definite loops only", ["definite", "indefinite"], "all")
    assert not ok and found == ["definite"] and missing == ["indefinite"]


def test_match_any_needs_one_keyword():
    assert ev.check_keywords("definite loops", ["definite", "indefinite"], "any")[0]


def test_min_matches_overrides_match():
    keywords = ["Java", "Python", "PHP"]
    assert not ev.check_keywords("Only Python.", keywords, "any", min_matches=2)[0]
    assert ev.check_keywords("Python and PHP.", keywords, "any", min_matches=2)[0]


# ---------------- grading ----------------
Q = {"question": "What is the main processor?", "keywords": [["cpu", "processor"]],
     "match": "any", "priority": "critical", "forbidden": ev.NO_ANSWER}


def test_grade_pass():
    assert ev.grade_answer(Q, "The CPU is the main processor.")["status"] == "PASS"


def test_grade_fail_when_keywords_missing():
    result = ev.grade_answer(Q, "It is a chip.")
    assert result["status"] == "FAIL" and result["missing"] == ["cpu/processor"]


def test_grade_conflict_on_forbidden_phrase():
    result = ev.grade_answer(Q, "I don't know, maybe the CPU?")
    assert result["status"] == "CONFLICT"
    assert "forbidden phrase present" in result["problems"][0]


def test_grade_conflict_on_wrong_stance():
    q = {**Q, "forbidden": [], "stance": "affirm"}
    assert ev.grade_answer(q, "The CPU is not the main processor.")["status"] == "CONFLICT"


def test_detect_stance():
    assert ev.detect_stance("Options are available.", ["options"]) == "affirm"
    assert ev.detect_stance("Options are not available.", ["options"]) == "negate"
    assert ev.detect_stance("Options are here. Options aren't there.", ["options"]) == "mixed"


# ---------------- retrieval metrics ----------------
def passages(*texts):
    return [{"text": t, "source": "notes.pdf", "chunk": i} for i, t in enumerate(texts)]


def test_retrieval_rank_and_reciprocal_rank():
    q = {"question": "x", "keywords": ["mnemonics"]}
    r = ev.check_retrieval(q, passages("intro", "cpu", "assembly uses mnemonics"))
    assert r["first_rank"] == 3 and r["rr"] == pytest.approx(1 / 3) and r["hit_at_3"]


def test_retrieval_miss_beyond_top_3():
    q = {"question": "x", "keywords": ["mnemonics"]}
    r = ev.check_retrieval(q, passages("a", "b", "c", "mnemonics here"))
    assert not r["hit_at_3"] and r["recall_at_10"] and r["first_rank"] == 4


def test_retrieval_uses_context_keywords_when_given():
    q = {"question": "x", "keywords": [["2", "two"]], "match": "any",
         "context_keywords": ["main memory", "secondary memory"]}
    r = ev.check_retrieval(q, passages("two of everything", "main memory and secondary memory"))
    assert r["first_rank"] == 2      # "two" alone in passage 1 doesn't count


# ---------------- summary ----------------
def result(priority, status, rr=1.0):
    return {"priority": priority, "status": status, "retrieval_ms": 10,
            "retrieval": {"hit_at_3": rr > 0, "recall_at_10": rr > 0, "rr": rr}}


def test_summary_weighted_score_and_counts():
    s = ev.summarize([result("critical", "PASS"), result("high", "FAIL", 0.5), result("normal", "CONFLICT", 0)],
                     retrieval_only=False)
    assert (s["earned"], s["total"]) == (3, 6) and s["score"] == pytest.approx(0.5)
    assert s["counts"] == {"PASS": 1, "CONFLICT": 1, "FAIL": 1}
    assert s["mrr"] == pytest.approx(0.5) and s["critical_failures"] == []


def test_summary_lists_critical_failures():
    s = ev.summarize([{**result("critical", "FAIL"), "question": "Q1"}], retrieval_only=False)
    assert s["critical_failures"] == ["Q1"]


def test_claude_call_estimate():
    assert ev.claude_calls(6, 4, retrieval_only=True, use_judge=False) == 0
    assert ev.claude_calls(6, 4, retrieval_only=False, use_judge=True) == 48


# ---------------- reading question sets ----------------
CSV = (
    "question,keywords,match,priority,min_matches,forbidden\n"
    "What does assembly use?,mnemonics; binary code|machine code,all,high,,\n"
    "Name languages,Java;Python;PHP,any,normal,2,none\n"
)


def test_csv_splits_keywords_and_synonyms():
    q1, q2 = ev.parse_dataset("set.csv", CSV.encode())
    assert q1["keywords"] == ["mnemonics", ["binary code", "machine code"]]
    assert q1["forbidden"] == ev.NO_ANSWER          # blank -> the standard "I don't know" phrases
    assert q2["min_matches"] == 2 and q2["forbidden"] == []   # "none" -> no forbidden phrases


def test_csv_reports_the_bad_row():
    bad = "question,keywords,priority\nOK question,cpu,high\nAnother one,cpu,urgent\n"
    with pytest.raises(ValueError, match=r"Row 3: priority"):
        ev.parse_dataset("set.csv", bad.encode())


def test_csv_rejects_unknown_columns_and_missing_keywords():
    with pytest.raises(ValueError, match="Unknown column"):
        ev.parse_dataset("set.csv", b"question,keywords,colour\nWhat?,a,red\n")
    with pytest.raises(ValueError, match="keywords"):
        ev.parse_dataset("set.csv", b"question\nWhat is it?\n")


def test_csv_accepts_excel_bom():
    data = "﻿question,keywords\nWhat is a CPU?,processor\n".encode("utf-8")
    assert ev.parse_dataset("set.csv", data)[0]["question"] == "What is a CPU?"


def test_json_list_and_wrapped_forms():
    item = {"question": "What is a CPU?", "keywords": ["processor"]}
    assert len(ev.parse_dataset("a.json", json.dumps([item]).encode())) == 1
    assert len(ev.parse_dataset("a.json", json.dumps({"questions": [item]}).encode())) == 1


def test_json_rejects_typos_and_bad_regex():
    with pytest.raises(ValueError, match=r"Question 1: keyword"):
        ev.parse_dataset("a.json", json.dumps([{"question": "What?", "keyword": ["x"]}]).encode())
    with pytest.raises(ValueError, match="invalid regex"):
        ev.parse_dataset("a.json", json.dumps(
            [{"question": "What?", "keywords": ["x"], "patterns": ["("]}]).encode())


def test_rejects_wrong_type_empty_and_too_many():
    with pytest.raises(ValueError, match=".csv or .json"):
        ev.parse_dataset("set.xlsx", b"x")
    with pytest.raises(ValueError, match="no questions"):
        ev.parse_dataset("a.json", b"[]")
    many = [{"question": f"Question {i}?", "keywords": ["x"]} for i in range(ev.MAX_QUESTIONS + 1)]
    with pytest.raises(ValueError, match="Too many"):
        ev.parse_dataset("a.json", json.dumps(many).encode())


def test_default_set_is_valid():
    questions = ev.load_default_set()
    assert len(questions) >= 6
    assert all(q["priority"] in ev.PRIORITY_WEIGHTS for q in questions)
