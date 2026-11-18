# doc-chat: Chat With Your Documents (RAG)

A small Retrieval-Augmented Generation (RAG) app. Drop PDFs or text files into a folder, index them, then ask questions in the terminal. The app finds the most relevant passages and has Claude answer using only those passages.

```
Your files → split into chunks → vector database (Chroma)
Question → find 3 closest chunks → send chunks + question to Claude → answer
```

## Features

- Ingests `.pdf` and `.txt` files from `data/`
- Overlapping word-based chunking
- Local vector storage with ChromaDB (no separate server needed)
- Answers grounded in your documents, with source names
- Evaluation script with keyword groups, priorities, forbidden phrases and an optional LLM judge

## Requirements

- Python 3.10+
- Git
- An Anthropic API key (console.anthropic.com)

## Setup

### 1. Clone the repository

```bash
git clone https://github.com/YOUR-USERNAME/doc-chat.git
cd doc-chat
```

### 2. Create and activate a virtual environment

```bash
python -m venv .venv
```

| OS / shell | Activate command |
|---|---|
| Windows PowerShell | `.venv\Scripts\Activate.ps1` |
| Windows cmd | `.venv\Scripts\activate.bat` |
| macOS / Linux | `source .venv/bin/activate` |

You should see `(.venv)` at the start of your prompt. Re-activate in every new terminal.

> PowerShell "scripts disabled" error? Run `Set-ExecutionPolicy -Scope Process Bypass` and try again.

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Add your API key

Create a file named `.env` in the project root:

```
ANTHROPIC_API_KEY=sk-ant-your-key-here
```

No quotes, no spaces around `=`. `.env` is listed in `.gitignore`, so it is never committed.

### 5. Add documents

Put your `.pdf` or `.txt` files in the `data/` folder. Text-based PDFs work best; scanned image PDFs need OCR first.

## Usage

Run all commands from the project root, with the virtual environment active.

**Index your documents** (run again whenever the files in `data/` change):

```bash
python src/ingest.py
```

**Ask a question:**

```bash
python src/query.py "What is this document mainly about?"
```

Or run it without arguments and type the question when prompted.

**Run the evaluation:**

```bash
python tests/eval.py
```

## Project structure

```
doc-chat/
├── README.md
├── requirements.txt
├── .env                 # API key (not committed)
├── .gitignore
├── data/                # your PDFs / .txt files
├── chroma_db/           # generated vector database (not committed)
├── src/
│   ├── ingest.py        # files → chunks → database
│   └── query.py         # question → retrieve → Claude answers
└── tests/
    └── eval.py          # scored test questions
```

## Configuration

| Setting | File | Default | Effect |
|---|---|---|---|
| `CHUNK_WORDS` | `src/ingest.py` | 400 | Words per chunk. Smaller = more precise, larger = more context |
| `OVERLAP_WORDS` | `src/ingest.py` | 50 | Words shared between neighbouring chunks |
| `N_RESULTS` | `src/query.py` | 3 | Chunks retrieved per question |
| `MODEL` | `src/query.py` | `claude-sonnet-5-5` | Claude model used to answer |
| `max_tokens` | `src/query.py` | 3000 | Answer length limit (thinking tokens count toward it) |
| `JUDGE_MODE` | `tests/eval.py` | `"off"` | `"on_pass"` adds an LLM check on passing tests |

If you change `CHUNK_WORDS` or `OVERLAP_WORDS`, delete the `chroma_db/` folder before running `ingest.py` again so old chunks don't linger.

## Evaluation

`tests/eval.py` runs a list of questions and checks each answer against:

- **Keywords:** strings, or lists of synonyms, matched as whole words
- **Match mode:** `all` keywords required, `any` one is enough, or `min_matches` for "at least N"
- **Priority:** `critical` (3 points), `high` (2), `normal` (1), with a weighted score
- **Forbidden phrases:** wording that marks an answer wrong, such as "I don't know"
- **Stance check:** flags answers that contain the keywords but say the opposite
- **Optional LLM judge:** compares meaning against a reference sentence

Statuses are `PASS`, `FAIL` (keywords missing) and `CONFLICT` (keywords present but meaning looks wrong).

### Results log

| Date | Chunk words | Results | Weighted score | Notes |
|---|---|---|---|---|
| YYYY-MM-DD | 400 | 3 | _/_ | baseline |

## Troubleshooting

| Problem | Fix |
|---|---|
| `python` not found | Use `python3`, or reinstall with "Add to PATH" ticked |
| `(.venv)` missing from prompt | Re-run the activate command |
| `ModuleNotFoundError` | Activate the venv, then `pip install -r requirements.txt` |
| `401 authentication_error` | Check `.env`; also check for a conflicting `ANTHROPIC_AUTH_TOKEN` or `ANTHROPIC_API_KEY` environment variable |
| `'ThinkingBlock' has no attribute 'text'` | Join only the blocks where `block.type == "text"` |
| Model not found | Check current model names at docs.claude.com |
| Empty answers from a PDF | The PDF is probably scanned images; OCR it first |
| `FileNotFoundError: data` | Run commands from the project root |

## Git workflow

`main` always holds the last working version of the app. New work happens on a separate branch and is merged back only when it works.

### One-time: mark the working baseline

```bash
git checkout main
git pull
git tag v0.1-base
git push origin v0.1-base
```

The tag is a permanent bookmark, so you can always return to the base RAG app.

### Start a new feature branch

```bash
git checkout main
git pull                          # get the latest main
git checkout -b feature/api       # create and switch to the new branch
```

`git switch -c feature/api` does the same thing in newer Git versions.

**Naming convention:**

| Prefix | Use for | Example |
|---|---|---|
| `feature/` | new functionality | `feature/streamlit-ui` |
| `fix/` | bug fixes | `fix/pdf-empty-text` |
| `experiment/` | things that may be thrown away | `experiment/bigger-chunks` |
| `docs/` | README or documentation only | `docs/update-setup` |

### Work and save progress

```bash
git status                        # what changed?
git add .
git commit -m "Add /ask endpoint"
```

Commit small and often, with messages that say what changed. Check `git status` before committing: `.env`, `.venv/` and `chroma_db/` must not appear.

### Push the branch to GitHub

First push of a new branch:

```bash
git push -u origin feature/api
```

After that, `git push` is enough.

### Merge it back into main

**Option A: Pull Request (recommended).** On github.com, click "Compare & pull request" for your branch, review the changes, then click "Merge".

**Option B: merge locally.**

```bash
git checkout main
git pull
git merge feature/api
git push
```

Then clean up:

```bash
git branch -d feature/api               # delete locally
git push origin --delete feature/api    # delete on GitHub
```

### Everyday commands

| Task | Command |
|---|---|
| List branches | `git branch` |
| Switch branch | `git checkout branch-name` |
| See branch history | `git log --oneline --graph --all` |
| Save unfinished work to switch branches | `git stash`, then later `git stash pop` |
| Bring latest `main` into your branch | `git checkout feature/api` then `git merge main` |
| Discard uncommitted changes to one file | `git restore path/to/file` |
| Undo the last commit, keep the changes | `git reset --soft HEAD~1` |
| Return to the base version | `git checkout v0.1-base` (then `git checkout main` to come back) |

### If you get a merge conflict

Git marks the clashing lines in the file:

```
<<<<<<< HEAD
your version
=======
their version
>>>>>>> main
```

Edit the file to keep what you want and delete the marker lines. Then run `git add file-name` and `git commit`. VS Code shows "Accept Current / Incoming / Both" buttons above each conflict.

### Rules of thumb

1. Never commit directly to `main` once the base app works.
2. One branch per feature or experiment.
3. Run `python tests/eval.py` before merging, and make sure the score hasn't dropped.
4. Never commit secrets. If a key is committed by accident, revoke it immediately and create a new one; deleting the file later does not remove it from history.

## Roadmap

- [ ] FastAPI backend (`feature/api`)
- [ ] Web frontend
- [ ] Show sources and chunk text in answers
- [ ] Conversation memory
- [ ] Expand evaluation question set
