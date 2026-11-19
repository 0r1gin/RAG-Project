"""Scoring the app: grade answers, measure retrieval, read question sets, run a set.

Used by the admin dashboard (admin.py) and the terminal (cli.py eval).
Everything here except evaluate()/run_set()/judge() works offline, so it can be unit-tested.

A question set is a list of questions like:
    {"question": "What are the 2 kinds of loops",
     "keywords": [["definite", "definite loops"], ["indefinite", "indefinite loops"]],
     "match": "all", "priority": "high"}

Retrieval metrics (per mode):
    hit@3     the 3 passages Claude sees contain the expected keywords
    recall@10 the top 10 passages contain them
    MRR       1 / rank of the first single passage that contains them (0 if none in the top 10)
"""
import csv
import io
import json
import re
import time
from pathlib import Path
from typing import Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from retrieval import N_RESULTS

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SET = ROOT / "tests" / "questions.json"

PRIORITY_WEIGHTS = {"critical": 3, "high": 2, "normal": 1}
RETRIEVAL_DEPTH = 10
MAX_QUESTIONS = 100
MAX_FILE_BYTES = 1024 * 1024
ANSWER_LIMIT = 1500          # characters of each answer kept in saved results

# Phrases that mean the app failed to find an answer. Used when a question sets no "forbidden".
NO_ANSWER = [
    "i don't know", "i do not know", "does not contain", "doesn't contain",
    "not mentioned", "no information",
]

NEGATION_WORDS = {
    "not", "no", "never", "none", "cannot", "without", "neither", "nor",
    "unavailable", "unable", "unsupported", "impossible", "incorrect",
    "false", "lack", "lacks", "missing",
}


# ================= QUESTION SETS =================
Keyword = Union[str, list[str]]   # a word, or a list of synonyms where any one counts


class Question(BaseModel):
    """One evaluation question. Unknown fields are rejected, so typos surface as errors."""
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=3, max_length=500)
    keywords: list[Keyword] = Field(min_length=1)
    match: Literal["all", "any"] = "all"
    min_matches: Optional[int] = Field(default=None, ge=1)
    priority: Literal["critical", "high", "normal"] = "normal"
    forbidden: list[str] = Field(default_factory=lambda: list(NO_ANSWER))
    patterns: list[str] = []
    stance: Optional[Literal["affirm", "negate"]] = None
    reference: str = ""
    context_keywords: Optional[list[Keyword]] = None   # what the passages must contain, if different

    @field_validator("keywords", "context_keywords")
    @classmethod
    def _no_blank_keywords(cls, value):
        for kw in value or []:
            words = [kw] if isinstance(kw, str) else kw
            if not words or any(not w.strip() for w in words):
                raise ValueError("keywords cannot be blank")
        return value

    @field_validator("patterns")
    @classmethod
    def _valid_regexes(cls, value):
        for pattern in value:
            try:
                re.compile(pattern)
            except re.error as e:
                raise ValueError(f"invalid regex {pattern!r}: {e}")
        return value


def _error_text(e: ValidationError) -> str:
    first = e.errors()[0]
    field = ".".join(str(part) for part in first["loc"]) or "question"
    return f"{field}: {first['msg']}"


def _split_keywords(cell: str) -> list[Keyword]:
    """'mnemonics; binary code|machine code' -> ['mnemonics', ['binary code', 'machine code']]"""
    items = []
    for item in cell.split(";"):
        words = [w.strip() for w in item.split("|") if w.strip()]
        if words:
            items.append(words[0] if len(words) == 1 else words)
    return items


CSV_COLUMNS = ["question", "keywords", "match", "min_matches", "priority",
               "forbidden", "reference", "context_keywords", "patterns", "stance"]


def _csv_rows(text: str) -> list[tuple[str, dict]]:
    reader = csv.DictReader(io.StringIO(text))
    headers = [(h or "").strip().lower() for h in (reader.fieldnames or [])]
    if "question" not in headers or "keywords" not in headers:
        raise ValueError("The CSV needs at least a 'question' and a 'keywords' column")
    unknown = [h for h in headers if h and h not in CSV_COLUMNS]
    if unknown:
        raise ValueError(f"Unknown column(s): {', '.join(unknown)}. Allowed: {', '.join(CSV_COLUMNS)}")

    rows = []
    for line_no, raw in enumerate(reader, start=2):        # row 1 is the header
        cells = {(k or "").strip().lower(): (v or "").strip() for k, v in raw.items() if k}
        if not any(cells.values()):
            continue                                        # skip blank lines
        q = {"question": cells.get("question", ""), "keywords": _split_keywords(cells.get("keywords", ""))}
        for key in ("match", "priority", "stance"):
            if cells.get(key):
                q[key] = cells[key].lower()
        if cells.get("min_matches"):
            q["min_matches"] = cells["min_matches"]
        if cells.get("reference"):
            q["reference"] = cells["reference"]
        if cells.get("context_keywords"):
            q["context_keywords"] = _split_keywords(cells["context_keywords"])
        if cells.get("patterns"):
            q["patterns"] = [p.strip() for p in cells["patterns"].split(";") if p.strip()]
        forbidden = cells.get("forbidden", "")
        if forbidden.lower() == "none":
            q["forbidden"] = []
        elif forbidden:
            q["forbidden"] = [p.strip() for p in forbidden.split(";") if p.strip()]
        rows.append((f"Row {line_no}", q))
    return rows


def _json_rows(text: str) -> list[tuple[str, dict]]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"Not valid JSON (line {e.lineno}): {e.msg}")
    if isinstance(data, dict):
        data = data.get("questions")
    if not isinstance(data, list):
        raise ValueError('The JSON must be a list of questions, or {"questions": [...]}')
    rows = []
    for i, item in enumerate(data, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"Question {i}: must be an object")
        rows.append((f"Question {i}", item))
    return rows


def parse_dataset(filename: str, data: bytes) -> list[dict]:
    """Read a .csv or .json question set. Raises ValueError with a message the admin can act on."""
    if len(data) > MAX_FILE_BYTES:
        raise ValueError("File too large (max 1 MB)")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ValueError("The file must be UTF-8 text")

    name = filename.lower()
    if name.endswith(".csv"):
        rows = _csv_rows(text)
    elif name.endswith(".json"):
        rows = _json_rows(text)
    else:
        raise ValueError("Upload a .csv or .json file")

    if not rows:
        raise ValueError("The file has no questions")
    if len(rows) > MAX_QUESTIONS:
        raise ValueError(f"Too many questions ({len(rows)}); the limit is {MAX_QUESTIONS} per set")

    questions = []
    for where, raw in rows:
        try:
            questions.append(Question.model_validate(raw).model_dump(exclude_none=True))
        except ValidationError as e:
            raise ValueError(f"{where}: {_error_text(e)}")
    return questions


def load_default_set() -> list[dict]:
    return parse_dataset(DEFAULT_SET.name, DEFAULT_SET.read_bytes())


# ================= MATCHING =================
def term_in(text: str, term: str) -> bool:
    """Whole-word, case-insensitive match."""
    return re.search(rf"(?<!\w){re.escape(term)}(?!\w)", text, re.IGNORECASE) is not None


def match_keyword(text: str, keyword) -> Optional[str]:
    """keyword is a string or a list of synonyms. Returns the matched term or None."""
    alternatives = [keyword] if isinstance(keyword, str) else keyword
    for alt in alternatives:
        if term_in(text, alt):
            return alt
    return None


def label(keyword) -> str:
    return keyword if isinstance(keyword, str) else "/".join(keyword)


def check_keywords(text: str, keywords, match: str = "all", min_matches=None):
    """Applies a question's keyword rule to text. Returns (ok, found, missing)."""
    found, missing = [], []
    for kw in keywords:
        hit = match_keyword(text, kw)
        if hit:
            found.append(hit)
        else:
            missing.append(label(kw))
    if min_matches:
        ok = len(found) >= min_matches
    elif match == "all":
        ok = not missing
    else:
        ok = bool(found)
    return ok, found, missing


# ---------------- stance ----------------
def split_sentences(text: str):
    return [s for s in re.split(r"(?<=[.!?])\s+|\n+", text) if s.strip()]


def count_negations(sentence: str) -> int:
    tokens = re.findall(r"[a-z']+", sentence.lower())
    return sum(1 for t in tokens if t in NEGATION_WORDS or t.endswith("n't"))


def detect_stance(text: str, matched_terms) -> str:
    """
    Looks at every sentence containing a matched keyword.
    Odd number of negation words -> 'negate', even -> 'affirm'.
    Returns 'affirm', 'negate', 'mixed' (sentences disagree) or 'unknown'.
    """
    stances = set()
    for sentence in split_sentences(text):
        if any(term_in(sentence, t) for t in matched_terms):
            stances.add("negate" if count_negations(sentence) % 2 else "affirm")
    if not stances:
        return "unknown"
    if len(stances) > 1:
        return "mixed"
    return stances.pop()


# ================= GRADING =================
def check_retrieval(q: dict, passages: list[dict]) -> dict:
    """Did retrieval surface the evidence? Judged on the passages, before Claude sees them."""
    keywords = q.get("context_keywords") or q["keywords"]
    rule = dict(match=q.get("match", "all"), min_matches=q.get("min_matches"))

    def ok(text):
        return check_keywords(text, keywords, **rule)[0]

    texts = [p["text"] for p in passages]
    first = next((i for i, t in enumerate(texts, start=1) if ok(t)), None)
    return {
        "hit_at_3": ok("\n".join(texts[:N_RESULTS])),
        "recall_at_10": ok("\n".join(texts[:RETRIEVAL_DEPTH])),
        "rr": 1.0 / first if first else 0.0,
        "first_rank": first,
        "top_sources": [f"{p['source']}#{p['chunk']}" for p in passages[:N_RESULTS]],
    }


def judge(q: dict, candidate: str):
    """Ask Claude whether the answer agrees with the reference. Returns a dict or None."""
    from query import MODEL, llm   # imported here so the rest of this module works offline

    expected = q.get("reference") or (
        "The answer should clearly cover: " + ", ".join(label(k) for k in q["keywords"])
    )
    prompt = (
        "You are grading an answer to a question.\n\n"
        f"Question: {q['question']}\n\n"
        f"Reference / expected content: {expected}\n\n"
        f"Candidate answer: {candidate}\n\n"
        "Does the candidate agree with the reference in meaning? Check direction "
        "(available vs unavailable, true vs false), numbers, and whether it contradicts "
        "itself. Mentioning the right words is NOT enough.\n"
        'Reply with ONLY JSON: {"verdict": "correct" or "incorrect", "reason": "one sentence"}'
    )
    try:
        response = llm.messages.create(
            model=MODEL, max_tokens=2000, messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(b.text for b in response.content if b.type == "text")
        return json.loads(re.sub(r"```json|```", "", text).strip())
    except Exception as e:
        print(f"   (judge failed: {e})")
        return None


def grade_answer(q: dict, text: str, use_judge: bool = False) -> dict:
    """Keywords, forbidden phrases, patterns, stance and the optional judge -> PASS/FAIL/CONFLICT."""
    ok, found, missing = check_keywords(text, q["keywords"], q.get("match", "all"), q.get("min_matches"))

    problems = []
    for phrase in q.get("forbidden", NO_ANSWER):
        if term_in(text, phrase):
            problems.append(f"forbidden phrase present: '{phrase}'")
    for pattern in q.get("patterns", []):
        if not re.search(pattern, text, re.IGNORECASE):
            problems.append(f"required pattern not matched: {pattern}")
    expected_stance = q.get("stance")
    if expected_stance and found:
        observed = detect_stance(text, found)
        if observed != expected_stance:
            problems.append(f"stance is '{observed}', expected '{expected_stance}'")

    if not ok:
        status = "FAIL"
    elif problems:
        status = "CONFLICT"      # keywords present, but meaning looks wrong
    else:
        status = "PASS"

    if status == "PASS" and use_judge:
        verdict = judge(q, text)
        if verdict and verdict.get("verdict") != "correct":
            status = "CONFLICT"
            problems.append("judge: " + verdict.get("reason", "marked incorrect"))

    return {"status": status, "found": found, "missing": missing, "problems": problems}


# ================= RUNNING =================
def evaluate(q: dict, mode: str, retrieval_only: bool = False, use_judge: bool = False) -> dict:
    from query import answer_with_context, retrieve

    started = time.perf_counter()
    deep = retrieve(q["question"], mode, k=RETRIEVAL_DEPTH)
    result = {
        "question": q["question"],
        "priority": q.get("priority", "normal"),
        "mode": mode,
        "retrieval": check_retrieval(q, deep),
        "retrieval_ms": round((time.perf_counter() - started) * 1000),
    }
    if not retrieval_only:
        # The answer path retrieves its own top 3; with a deterministic index it equals deep[:3].
        answer = answer_with_context(q["question"], mode)["answer"]
        result.update(grade_answer(q, answer, use_judge))
        result["answer"] = answer[:ANSWER_LIMIT]
    return result


def summarize(results: list[dict], retrieval_only: bool) -> dict:
    n = len(results) or 1
    summary = {
        "tests": len(results),
        "hit_at_3": sum(r["retrieval"]["hit_at_3"] for r in results) / n,
        "recall_at_10": sum(r["retrieval"]["recall_at_10"] for r in results) / n,
        "mrr": sum(r["retrieval"]["rr"] for r in results) / n,
        "avg_retrieval_ms": sum(r["retrieval_ms"] for r in results) / n,
    }
    if not retrieval_only:
        earned = total = 0
        by_priority = {p: [0, 0] for p in PRIORITY_WEIGHTS}   # [passed, total]
        counts = {"PASS": 0, "CONFLICT": 0, "FAIL": 0}
        for r in results:
            weight = PRIORITY_WEIGHTS[r["priority"]]
            total += weight
            by_priority[r["priority"]][1] += 1
            counts[r["status"]] += 1
            if r["status"] == "PASS":
                earned += weight
                by_priority[r["priority"]][0] += 1
        summary.update(
            score=earned / total if total else 0.0,
            earned=earned,
            total=total,
            counts=counts,
            by_priority={p: v for p, v in by_priority.items() if v[1]},
            critical_failures=[r["question"] for r in results
                               if r["priority"] == "critical" and r["status"] != "PASS"],
        )
    return summary


def usable_modes(modes: list[str]) -> tuple[list[str], str]:
    """Drops the +rerank modes if the reranker model can't load. Returns (modes, warning)."""
    if not any(m.endswith("+rerank") for m in modes):
        return modes, ""
    from query import reranker
    try:
        reranker.load()
        return modes, ""
    except Exception as e:
        kept = [m for m in modes if not m.endswith("+rerank")]
        return kept, f"Reranker unavailable ({e}); skipped the +rerank modes."


def claude_calls(n_questions: int, n_modes: int, retrieval_only: bool, use_judge: bool) -> int:
    """Upper bound on Claude requests a run makes (shown before running)."""
    if retrieval_only:
        return 0
    return n_questions * n_modes * (2 if use_judge else 1)


def run_set(questions: list[dict], modes: list[str], retrieval_only: bool = False,
            use_judge: bool = False, on_progress=None) -> dict:
    """Runs every question in every mode. on_progress(done, total) is called after each one."""
    ordered = sorted(questions, key=lambda q: -PRIORITY_WEIGHTS[q.get("priority", "normal")])
    total, done = len(ordered) * len(modes), 0
    results, summaries = {}, {}
    for mode in modes:
        mode_results = []
        for q in ordered:
            mode_results.append(evaluate(q, mode, retrieval_only, use_judge))
            done += 1
            if on_progress:
                on_progress(done, total)
        results[mode] = mode_results
        summaries[mode] = summarize(mode_results, retrieval_only)
    return {"summaries": summaries, "results": results}
