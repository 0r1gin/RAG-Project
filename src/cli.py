"""Terminal commands. Run from the project root:

    python src/cli.py hash-password            # make ADMIN_PASSWORD_HASH for .env
    python src/cli.py link-telegram            # find TELEGRAM_ADMIN_CHAT_ID for .env
    python src/cli.py upload-folder [data]     # upload every PDF/TXT in a folder
    python src/cli.py eval [options]           # score the app (see: python src/cli.py eval -h)
"""
import argparse
import getpass
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.chdir(ROOT)                    # .env, chroma_db and the Firebase key are relative to the project root
sys.path.insert(0, str(ROOT / "src"))


# ---------------- hash-password ----------------
def hash_password(_args):
    from argon2 import PasswordHasher

    password = getpass.getpass("New admin password: ")
    if password != getpass.getpass("Repeat password: "):
        sys.exit("Passwords do not match")
    if len(password) < 12:
        sys.exit("Use at least 12 characters")
    print(PasswordHasher().hash(password))


# ---------------- link-telegram ----------------
def link_telegram(_args):
    """Finds the chat id of the Telegram account named in ADMIN_TELEGRAM_HANDLE."""
    import httpx
    from dotenv import load_dotenv

    load_dotenv()
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    handle = os.environ["ADMIN_TELEGRAM_HANDLE"].lstrip("@").lower()
    try:
        data = httpx.get(f"https://api.telegram.org/bot{token}/getUpdates", timeout=15).json()
    except httpx.HTTPError:
        sys.exit("Could not reach Telegram")
    if not data.get("ok"):
        sys.exit(f"Telegram rejected the request: {data.get('description')}")

    for update in data["result"]:
        message = update.get("message") or {}
        sender = message.get("from") or {}
        chat = message.get("chat") or {}
        if (sender.get("username") or "").lower() == handle and chat.get("type") == "private":
            print(f"Found @{handle}. Add this line to .env:")
            print(f"TELEGRAM_ADMIN_CHAT_ID={chat['id']}")
            return
    sys.exit(f"No message from @{handle} yet. Open your bot, press Start, then run this again.")


# ---------------- upload-folder ----------------
def upload_folder(args):
    import documents

    folder = Path(args.folder)
    files = [p for p in sorted(folder.iterdir()) if p.suffix.lower() in documents.ALLOWED_EXTENSIONS]
    if not files:
        sys.exit(f"No .pdf or .txt files in {folder}/")
    for path in files:
        print(documents.add_document(path.name, path.read_bytes()))


# ---------------- eval ----------------
def print_details(mode: str, results: list[dict], retrieval_only: bool):
    print(f"\n=== {mode} ===")
    for r in results:
        ret = r["retrieval"]
        evidence = "evidence@3 yes" if ret["hit_at_3"] else "evidence@3 NO "
        status = "" if retrieval_only else f"[{r['status']}] "
        print(f"{status}({r['priority']}) {r['question']}   "
              f"[{evidence} | first rank {ret['first_rank'] or '-'}]")
        if not retrieval_only and r["status"] != "PASS":
            if r["missing"]:
                print(f"    missing keywords: {r['missing']}")
            for p in r["problems"]:
                print(f"    problem: {p}")
            print(f"    ANSWER: {r['answer'][:300]}")
        if not ret["hit_at_3"]:
            print(f"    top passages: {', '.join(ret['top_sources']) or 'none'}")


def print_comparison(summaries: dict, production: str, retrieval_only: bool):
    cols = ["mode", "hit@3", "recall@10", "MRR", "ms"] + ([] if retrieval_only else ["score", "points"])
    rows = []
    for mode, s in summaries.items():
        row = [mode + (" *" if mode == production else ""), f"{s['hit_at_3']:.0%}",
               f"{s['recall_at_10']:.0%}", f"{s['mrr']:.2f}", f"{s['avg_retrieval_ms']:.0f}"]
        if not retrieval_only:
            row += [f"{s['score']:.0%}", f"{s['earned']}/{s['total']}"]
        rows.append(row)
    widths = [max(len(str(x)) for x in col) for col in zip(cols, *rows)]

    def line(cells):
        return "  ".join(str(c).ljust(w) for c, w in zip(cells, widths))

    print("\n--- Comparison (* = production mode) ---")
    print(line(cols))
    print(line(["-" * w for w in widths]))
    for row in rows:
        print(line(row))


def run_eval(args):
    import evaluation
    import query

    modes = [m.strip() for m in args.modes.split(",") if m.strip()]
    unknown = [m for m in modes if m not in query.RETRIEVAL_MODES]
    if unknown:
        sys.exit(f"Unknown mode(s): {', '.join(unknown)}. Choose from {', '.join(query.RETRIEVAL_MODES)}")
    try:
        questions = (evaluation.parse_dataset(Path(args.dataset).name, Path(args.dataset).read_bytes())
                     if args.dataset else evaluation.load_default_set())
    except (OSError, ValueError) as e:
        sys.exit(f"Could not read the question set: {e}")

    modes, warning = evaluation.usable_modes(modes)
    if warning:
        print(warning + "\n")
    if not modes:
        sys.exit(2)

    calls = evaluation.claude_calls(len(questions), len(modes), args.retrieval_only, args.judge)
    print(f"{len(questions)} questions x {len(modes)} mode(s), up to {calls} Claude call(s)")
    out = evaluation.run_set(questions, modes, args.retrieval_only, args.judge)

    for mode in modes:
        print_details(mode, out["results"][mode], args.retrieval_only)
    print_comparison(out["summaries"], query.DEFAULT_MODE, args.retrieval_only)

    if args.json:
        Path(args.json).write_text(json.dumps(
            {"model": query.MODEL, "production_mode": query.DEFAULT_MODE, **out}, indent=2), encoding="utf-8")
        print(f"\nWrote {args.json}")

    # Exit code for CI: judged on the production mode, or the first mode run.
    gate = query.DEFAULT_MODE if query.DEFAULT_MODE in out["summaries"] else modes[0]
    s = out["summaries"][gate]
    failed = False
    if s.get("critical_failures"):
        print(f"\nCRITICAL FAILURES ({gate}):")
        for q in s["critical_failures"]:
            print("  -", q)
        failed = True
    metric = "mrr" if args.retrieval_only else "score"
    if args.min_score is not None and s[metric] < args.min_score:
        print(f"\n{gate} {metric} {s[metric]:.2f} is below the minimum {args.min_score:.2f}")
        failed = True
    sys.exit(1 if failed else 0)


def main():
    parser = argparse.ArgumentParser(description="doc-chat terminal commands")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("hash-password", help="make ADMIN_PASSWORD_HASH for .env").set_defaults(func=hash_password)
    sub.add_parser("link-telegram", help="find TELEGRAM_ADMIN_CHAT_ID for .env").set_defaults(func=link_telegram)

    up = sub.add_parser("upload-folder", help="upload every PDF/TXT in a folder")
    up.add_argument("folder", nargs="?", default="data")
    up.set_defaults(func=upload_folder)

    ev = sub.add_parser("eval", help="score retrieval and answers")
    ev.add_argument("--dataset", metavar="FILE", help="a .csv or .json question set (default: tests/questions.json)")
    ev.add_argument("--modes", default="vector,vector+rerank,hybrid,hybrid+rerank",
                    help="comma-separated retrieval modes")
    ev.add_argument("--retrieval-only", action="store_true", help="skip Claude; score retrieval only (free)")
    ev.add_argument("--judge", action="store_true", help="ask Claude to double-check passing answers")
    ev.add_argument("--json", metavar="PATH", help="save full results as JSON")
    ev.add_argument("--min-score", type=float, metavar="X",
                    help="exit 1 if the production mode's score (or MRR with --retrieval-only) is below X (0-1)")
    ev.set_defaults(func=run_eval)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
