import json
import re
import sys

sys.path.insert(0, "src")
from query import answer, llm, MODEL   # reuse your Claude client for the judge

# ---------------- CONFIG ----------------
PRIORITY_WEIGHTS = {"critical": 3, "high": 2, "normal": 1}

# "off"     = heuristics only (free, fast)
# "on_pass" = after a test passes the heuristics, ask Claude to double-check it
JUDGE_MODE = "off"

NEGATION_WORDS = {
    "not", "no", "never", "none", "cannot", "without", "neither", "nor",
    "unavailable", "unable", "unsupported", "impossible", "incorrect",
    "false", "lack", "lacks", "missing",
}

# ---------------- TESTS ----------------
# keywords : list. Each item is a string OR a list of synonyms (any one counts).
# match    : "all"  -> every keyword item must appear
#            "any"  -> at least one keyword item must appear
# priority : "critical" | "high" | "normal"
# forbidden: phrases that make the answer wrong if present (optional)
# patterns : regexes that must match the answer (optional)
# stance   : "affirm" | "negate" | None  -> expected polarity around the keywords
# reference: the correct answer in plain English, used by the judge (optional)

# Phrases that mean the app failed to find an answer. Reused by every test.
NO_ANSWER = [
    "i don't know", "i do not know", "does not contain", "doesn't contain",
    "not mentioned", "no information",
]

TESTS = [
    {
        "question": "How many memory components exists in a computer?",
        "keywords": [["2", "two"]],
        "match": "any",
        "priority": "high",
        "forbidden": NO_ANSWER,
        "reference": "A computer has 2 memory components.",
    },
    {
        "question": "What does assembly language use?",
        "keywords": ["mnemonics", ["binary code", "binary", "machine code"]],
        "match": "all",
        "priority": "high",
        "forbidden": NO_ANSWER,
        "reference": "Assembly language uses mnemonics and binary code.",
    },
    {
        "question": "List a few high level languages",
        "keywords": ["JavaScript", "Java", "C#", "PHP", "Python"],
        "match": "any",
        "min_matches": 2,          # "a few" -> at least 2 of the 5 (needs the patch below)
        "priority": "normal",
        "forbidden": NO_ANSWER,
        "reference": "High level languages include JavaScript, Java, C#, PHP and Python.",
    },
    {
        "question": "What are decision structures",
        "keywords": [
            ["decision", "decisions"],
            ["statement", "statements"],
            ["executed", "execute", "executes", "run"],
        ],
        "match": "all",
        "priority": "normal",
        "forbidden": NO_ANSWER,
        "reference": (
            "Decision structures are about decisions, specifically whether statements "
            "in a program are executed, such as whether to compute a discount on a payment."
        ),
    },
    {
        "question": "What are the 2 kinds of loops",
        "keywords": [
            ["definite", "definite loop", "definite loops"],
            ["indefinite", "indefinite loop", "indefinite loops"],
        ],
        "match": "all",
        "priority": "high",
        "forbidden": NO_ANSWER,
        "reference": "The two kinds of loops are definite loops and indefinite loops.",
    },
    {
        "question": "What is the main processor in a computer",
        "keywords": [["cpu", "central processing unit", "processor"]],
        "match": "any",
        "priority": "critical",
        "forbidden": NO_ANSWER,
        "reference": "The main processor is the CPU (central processing unit).",
    },
    # Example of a contradiction-sensitive test:
    # {
    #     "question": "Are all potential options available?",
    #     "keywords": ["potential options"],
    #     "match": "all",
    #     "priority": "normal",
    #     "stance": "affirm",
    #     "forbidden": ["unavailable", "not available"],
    #     "patterns": [r"potential options\s+(are|is)\s+available"],
    # },
]


# ---------------- MATCHING HELPERS ----------------
def term_in(text: str, term: str) -> bool:
    """Whole-word, case-insensitive match."""
    return re.search(rf"(?<!\w){re.escape(term)}(?!\w)", text, re.IGNORECASE) is not None


def match_keyword(text: str, keyword):
    """keyword is a string or a list of synonyms. Returns the matched term or None."""
    alternatives = [keyword] if isinstance(keyword, str) else keyword
    for alt in alternatives:
        if term_in(text, alt):
            return alt
    return None


def label(keyword) -> str:
    return keyword if isinstance(keyword, str) else "/".join(keyword)


# ---------------- STANCE / CONSENSUS ----------------
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


# ---------------- LLM JUDGE ----------------
def judge(question: str, candidate: str, test: dict):
    expected = test.get("reference") or (
        "The answer should clearly cover: " + ", ".join(label(k) for k in test["keywords"])
    )
    prompt = (
        "You are grading an answer to a question.\n\n"
        f"Question: {question}\n\n"
        f"Reference / expected content: {expected}\n\n"
        f"Candidate answer: {candidate}\n\n"
        "Does the candidate agree with the reference in meaning? Check direction "
        "(available vs unavailable, true vs false), numbers, and whether it contradicts "
        "itself. Mentioning the right words is NOT enough.\n"
        'Reply with ONLY JSON: {"verdict": "correct" or "incorrect", "reason": "one sentence"}'
    )
    try:
        response = llm.messages.create(
            model=MODEL,
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(b.text for b in response.content if b.type == "text")
        text = re.sub(r"```json|```", "", text).strip()
        return json.loads(text)
    except Exception as e:
        print(f"   (judge failed: {e})")
        return None


# ---------------- EVALUATION ----------------
def evaluate(test: dict) -> dict:
    question = test["question"]
    text = answer(question)
    mode = test.get("match", "all")

    found, missing = [], []
    for kw in test["keywords"]:
        hit = match_keyword(text, kw)
        if hit:
            found.append(hit)
        else:
            missing.append(label(kw))

    min_matches = test.get("min_matches")
    if min_matches:
        keywords_ok = len(found) >= min_matches
    elif mode == "all":
        keywords_ok = not missing
    else:
        keywords_ok = bool(found)

    problems = []
    for phrase in test.get("forbidden", []):
        if term_in(text, phrase):
            problems.append(f"forbidden phrase present: '{phrase}'")

    for pattern in test.get("patterns", []):
        if not re.search(pattern, text, re.IGNORECASE):
            problems.append(f"required pattern not matched: {pattern}")

    expected_stance = test.get("stance")
    if expected_stance and found:
        observed = detect_stance(text, found)
        if observed != expected_stance:
            problems.append(f"stance is '{observed}', expected '{expected_stance}'")

    if not keywords_ok:
        status = "FAIL"
    elif problems:
        status = "CONFLICT"      # keywords present, but meaning looks wrong
    else:
        status = "PASS"

    if status == "PASS" and JUDGE_MODE == "on_pass":
        verdict = judge(question, text, test)
        if verdict and verdict.get("verdict") != "correct":
            status = "CONFLICT"
            problems.append("judge: " + verdict.get("reason", "marked incorrect"))

    return {
        "test": test, "status": status, "answer": text,
        "found": found, "missing": missing, "problems": problems,
    }


def main():
    ordered = sorted(
        TESTS, key=lambda t: -PRIORITY_WEIGHTS[t.get("priority", "normal")]
    )
    results = [evaluate(t) for t in ordered]

    earned = total = 0
    by_priority = {p: [0, 0] for p in PRIORITY_WEIGHTS}   # [passed, total]
    critical_failures = []

    for r in results:
        t = r["test"]
        prio = t.get("priority", "normal")
        weight = PRIORITY_WEIGHTS[prio]
        total += weight
        by_priority[prio][1] += 1
        if r["status"] == "PASS":
            earned += weight
            by_priority[prio][0] += 1
        elif prio == "critical":
            critical_failures.append(t["question"])

        print(f"[{r['status']}] ({prio}) {t['question']}")
        if r["status"] != "PASS":
            if r["missing"]:
                print(f"    missing keywords ({t.get('match', 'all')}): {r['missing']}")
            for p in r["problems"]:
                print(f"    problem: {p}")
            print(f"    ANSWER: {r['answer'][:300]}")

    print("\n--- Summary ---")
    for prio, (p, n) in by_priority.items():
        if n:
            print(f"{prio:9s} {p}/{n}")
    print(f"Weighted score: {earned}/{total} ({earned / total:.0%})")

    if critical_failures:
        print("\nCRITICAL FAILURES:")
        for q in critical_failures:
            print("  -", q)
        sys.exit(1)


if __name__ == "__main__":
    main()