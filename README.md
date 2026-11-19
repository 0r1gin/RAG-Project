# doc-chat: Chat With Your Documents

Upload your PDF and text files, then ask questions about them in plain English. Claude answers **only from your documents** and tells you which file each answer came from. If the answer isn't in your files, it says so instead of guessing.

An admin panel lets you manage the documents and **test how accurate the answers are**, with charts that track the score over time.

> **Live demo:** _add your link here_ · **Screenshots:** _add `docs/chat.png`, `docs/admin.png` and `docs/eval.png`_

**Contents**
- [Part 1: Using the app](#part-1-using-the-app): quick start, asking questions, managing documents, the evaluation dashboard
- [Part 2: Understanding and changing the code](#part-2-understanding-and-changing-the-code): project structure, how it works, common changes
- [Part 3: Reference](#part-3-reference): settings, API, security, deployment, troubleshooting

---

# Part 1: Using the app

## Quick start

You need **Python 3.10+**, an **Anthropic API key**, a free **Firebase** project and a **Telegram** account with a public username. The full setup (about 15 minutes) is in [Setup in detail](#setup-in-detail). In short:

```bash
git clone https://github.com/YOUR-USERNAME/doc-chat.git
cd doc-chat
python -m venv .venv
.venv\Scripts\activate            # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
# create .env (see "Setup in detail"), then:
uvicorn api:app --app-dir src --reload --port 8000
```

Then open **http://localhost:8000**.

| Page | Address | Who |
|---|---|---|
| Chat | `http://localhost:8000/` | anyone |
| Admin sign-in | `http://localhost:8000/login.html` | admin |
| Documents | `http://localhost:8000/admin.html` | admin |
| Evaluation | `http://localhost:8000/eval.html` | admin |

The first start downloads a small ranking model (~90 MB) once.

## Asking questions

1. Open the chat page.
2. Type a question, or click one of the example questions, and press **Enter** (Shift+Enter adds a new line).
3. The answer appears with the **source files** it used. **Copy** copies the answer.

Each question is answered on its own; the app doesn't remember earlier questions. The badge in the top right shows whether the server is ready and how many passages are indexed.

## Signing in as admin

1. Go to `/login.html` and enter your username and password.
2. A 6-digit code arrives in your Telegram. Type it in; it submits by itself.
3. You stay signed in for 30 minutes. The **sign-out** icon at the bottom of the left bar ends the session.

## Managing documents

On the **Documents** page (folder icon):

- **Add:** drop files on the upload area or click it. PDF or TXT, up to 5 MB each, up to 20 at once. Each file shows its own result.
- **Find:** search by file name.
- **Remove:** **Delete** on a row removes the file and everything indexed from it.

A file with the same name as an existing one is skipped; delete the old one first to replace it. Scanned PDFs (pictures of text) can't be read without OCR.

## Testing accuracy: the Evaluation dashboard

The **Evaluation** page (chart icon) checks the assistant against a set of questions whose answers you know, and shows how well it did.

### Run an evaluation

1. Pick a **question set**. "Default questions" is built in; you can upload your own (below).
2. Pick the **retrieval modes** to compare (explained below). The one marked **live** is what the chat page uses.
3. Optional:
   - **Retrieval only**: free and fast. It checks whether the right passages were found and skips Claude.
   - **LLM judge**: Claude double-checks each passing answer for meaning, not just keywords.
4. Check the cost note (for example "up to 24 Claude calls"), then press **Run evaluation**. A progress bar shows how far it has got. You can leave the page and come back.

### Read the results

| You see | It means |
|---|---|
| **Answer score** | Share of questions answered correctly, weighted by priority (critical = 3 points, high = 2, normal = 1) |
| **Evidence found** | How often the passages given to Claude actually contained the answer |
| **MRR** | How high the right passage ranks; 1.00 means it was always first |
| **Retrieval time** | How long finding passages takes per question |
| **PASS / CONFLICT / FAIL** | Correct / right words but wrong meaning (e.g. "I don't know", or "not X" when X is expected) / missing the expected words |

- **Charts:** *Mode comparison* and *Results per mode* show the selected run; *Score history* shows the live mode across recent runs, so you can see whether a change helped or hurt.
- **Results by question:** click a row to see each mode's answer, what was missing, and which passages Claude saw.
- **Run history:** click any finished run to load it into the charts.

### The retrieval modes

| Mode | How passages are found | Speed |
|---|---|---|
| `vector` | by meaning only | fast |
| `vector+rerank` | by meaning, then re-ordered by a ranking model | about 1 s slower |
| `hybrid` | by meaning **and** by exact keywords, merged | fast |
| `hybrid+rerank` (default) | meaning + keywords, then re-ordered | about 1 s slower |

### Write your own question set

Click **CSV template** on the Evaluation page, fill it in with a spreadsheet, and upload it (CSV or JSON, up to 100 questions).

| Column | What to put | Example |
|---|---|---|
| `question` | the question | `What are the 2 kinds of loops?` |
| `keywords` | words a correct answer must contain. Separate items with `;` and give alternatives with `\|` | `definite; indefinite` or `2\|two` |
| `match` | `all` items needed, or `any` one | `all` |
| `min_matches` | for "name a few" questions: at least this many items | `2` |
| `priority` | `critical`, `high` or `normal` | `high` |
| `forbidden` | phrases that make the answer wrong, separated by `;`. Leave blank to reject "I don't know"-style answers; write `none` to allow anything | |
| `reference` | the correct answer in a sentence (used by the LLM judge) | `Definite and indefinite loops.` |
| `context_keywords` | what the *passages* must contain, if different from the answer keywords | `main memory; secondary memory` |

If a row has a problem, the upload names it, for example *"Row 4: priority: Input should be 'critical', 'high' or 'normal'"*.

**Tip:** write questions about every document you upload. A question set that only covers one file can't tell you how well the others are handled.

---

# Part 2: Understanding and changing the code

## Project structure

```
doc-chat/
├── requirements.txt          everything to install (app + tests)
├── .env                      your secrets (never committed)
├── frontend/                 the web pages: plain HTML, CSS and JavaScript, no build step
│   ├── index.html, app.js      chat page
│   ├── login.html, login.js    two-step sign-in
│   ├── admin.html, admin.js    documents page
│   ├── eval.html, eval.js      evaluation dashboard (charts use Chart.js)
│   ├── common.js               shared: theme, icons, notifications, admin API calls
│   └── style.css               all styling; colours are variables at the top
├── src/                      the Python backend (FastAPI)
│   ├── api.py                  starts the app; /ask and /health; serves the frontend
│   ├── query.py                finds passages for a question, then asks Claude
│   ├── retrieval.py            the search building blocks: keyword search, merging, reranking
│   ├── documents.py            reading, splitting and indexing uploaded files
│   ├── store.py                every Firestore read and write
│   ├── admin.py                all admin routes (documents and evaluation)
│   ├── evaluation.py           scoring: grading answers, retrieval metrics, reading question sets
│   ├── auth.py                 password check, session cookie, rate limiting
│   ├── otp.py                  Telegram one-time codes
│   └── cli.py                  terminal commands (setup helpers and the evaluation)
└── tests/
    ├── questions.json          the default evaluation questions
    ├── test_retrieval.py       unit tests for search
    └── test_evaluation.py      unit tests for scoring and question-set parsing
```

Generated and never committed: `chroma_db/` (search index), `.cache/` (ranking model), `.venv/`.

## How it works

```
 Browser                       FastAPI backend (src/)
 ├─ chat page  ── POST /ask ──► query.py: find passages ──► Claude ──► answer + sources
 ├─ documents  ── /api/admin ─► documents.py: read ► split ► save (Firestore) + index (Chroma)
 ├─ evaluation ── /api/admin ─► evaluation.py: run questions ► score ► save run (Firestore)
 └─ sign-in    ── /api/admin ─► auth.py + otp.py: password ► Telegram code ► session cookie

 On every start: Firestore ─► rebuild the Chroma search index
```

**Adding a document** (`documents.py`)
1. The text is extracted (`pypdf` for PDFs) and split into overlapping chunks of about 400 words.
2. The chunks are saved in **Firestore**, the permanent copy.
3. They are added to **Chroma**, the search index. If that fails, the Firestore copy is removed so the two never disagree.

**Answering a question** (`query.py`, using `retrieval.py`)
1. **Meaning search:** Chroma finds the 20 chunks closest in meaning to the question.
2. **Keyword search:** a BM25 index finds the 20 chunks that best match the exact words. It catches names, numbers and terms like `C#` that meaning search blurs.
3. **Merge:** the two lists are combined by rank (reciprocal rank fusion).
4. **Rerank:** a small local model (`ms-marco-MiniLM-L-6-v2`) reads the question with each of the top 10 chunks and re-orders them by how well they answer it.
5. **Answer:** Claude gets the best 3 chunks and is told to answer only from them.

**Why Firestore and Chroma?** Free hosts wipe their disk on restart. Firestore keeps the data safe; Chroma is rebuilt from it on every start.

## Common changes

| To change… | Edit | Notes |
|---|---|---|
| The Claude model | `MODEL` in `src/query.py` | |
| How answers are worded | `build_prompt()` in `src/query.py` | re-run the evaluation afterwards |
| The live retrieval mode | `RETRIEVAL_MODE` in `.env` | `vector`, `vector+rerank`, `hybrid` or `hybrid+rerank` |
| Chunks sent to Claude | `N_RESULTS` in `src/retrieval.py` | default 3 |
| Chunk size | `CHUNK_WORDS`, `OVERLAP_WORDS` in `src/documents.py` | re-upload documents afterwards |
| Example questions on the chat page | `SUGGESTIONS` in `frontend/app.js` | |
| Colours | variables at the top of `frontend/style.css` | light and dark sets |
| Default evaluation questions | `tests/questions.json` | same fields as the CSV columns |
| Upload limits | `MAX_BYTES` in `src/documents.py` **and** `frontend/admin.js` | keep them equal |

**A good habit:** before and after any change to retrieval, prompts or chunking, run an evaluation and compare the score history.

## Terminal commands

All from the project root, with the virtual environment active:

```bash
python src/cli.py hash-password          # make the admin password hash for .env
python src/cli.py link-telegram          # find your Telegram chat id for .env
python src/cli.py upload-folder data     # upload every PDF/TXT in a folder (once; twice makes duplicates)

python src/cli.py eval                   # evaluate every retrieval mode (uses Claude)
python src/cli.py eval --retrieval-only  # free: retrieval metrics only
python src/cli.py eval --modes hybrid+rerank --min-score 0.9   # exit code 1 if below 90%
python src/cli.py eval --dataset my-questions.csv --json results.json

pytest                                   # unit tests (no internet or API key needed)
```

`eval` exits with code 1 if a **critical** question fails, or if the score is under `--min-score`, so it can gate a CI pipeline. It reads the local search index, so start the server once first to build it.

---

# Part 3: Reference

## Setup in detail

**1. Install** (see [Quick start](#quick-start)). If PowerShell says scripts are disabled, run `Set-ExecutionPolicy -Scope Process Bypass` and activate again.

**2. Firebase**
1. Create a project at console.firebase.google.com (the free Spark plan is enough), then **Build → Firestore Database → Create database**.
2. Under **Rules**, block all direct access (only the backend uses the database):
   ```
   rules_version = '2';
   service cloud.firestore {
     match /databases/{database}/documents {
       match /{document=**} { allow read, write: if false; }
     }
   }
   ```
3. **Project settings → Service accounts → Generate new private key.** Save it in the project root as `serviceAccountKey.json`.

**3. Admin password and session secret**
```bash
python src/cli.py hash-password
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

**4. Telegram bot**
1. Message **@BotFather**, send `/newbot`, copy the token.
2. Open your new bot and press **Start**.
3. Fill in `.env` (next step), then run `python src/cli.py link-telegram` and add the `TELEGRAM_ADMIN_CHAT_ID=...` line it prints.

**5. Create `.env`** in the project root:
```
ANTHROPIC_API_KEY=sk-ant-...
FIREBASE_KEY_PATH=serviceAccountKey.json

ADMIN_USERNAME=choose-a-username
ADMIN_PASSWORD_HASH='$argon2id$v=19$m=65536,t=3,p=4$...'
JWT_SECRET=the-48-character-string-from-step-3
COOKIE_SECURE=false

TELEGRAM_BOT_TOKEN=123456789:AAH-your-token
ADMIN_TELEGRAM_HANDLE=your_telegram_username
TELEGRAM_ADMIN_CHAT_ID=123456789
```
Keep the single quotes around the hash (it contains `$`). No spaces around `=`. Restart the server after editing `.env`.

## Settings

| Setting | Where | Default | Effect |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | `.env` | | Claude access |
| `FIREBASE_KEY_PATH` / `FIREBASE_CREDENTIALS_JSON` | `.env` | | key file path locally / whole key file on a host |
| `ADMIN_USERNAME`, `ADMIN_PASSWORD_HASH` | `.env` | | admin sign-in |
| `JWT_SECRET` | `.env` | | signs sessions; 32+ characters |
| `COOKIE_SECURE` | `.env` | `false` | `true` on HTTPS hosts |
| `TELEGRAM_BOT_TOKEN`, `ADMIN_TELEGRAM_HANDLE`, `TELEGRAM_ADMIN_CHAT_ID` | `.env` | | second sign-in factor |
| `RETRIEVAL_MODE` | `.env` | `hybrid+rerank` | how passages are found |
| `RERANK_CANDIDATES` | `.env` | 10 | chunks the ranking model re-orders (~100 ms each on CPU) |
| `RERANK_MODEL` | `.env` | `Xenova/ms-marco-MiniLM-L-6-v2` | any reranker `fastembed` supports |
| `FASTEMBED_CACHE_PATH` | `.env` | `.cache/fastembed` | where the ranking model is stored |
| `MODEL`, `max_tokens` | `src/query.py` | `claude-sonnet-5-5`, 1000 | Claude model and answer length |
| `N_CANDIDATES` | `src/query.py` | 20 | chunks each search contributes before merging |
| `TOKEN_MINUTES` | `src/auth.py` | 30 | session length |
| `MAX_FAILURES`, `WINDOW_SECONDS` | `src/auth.py` | 5, 10 | failed sign-ins allowed per IP per window (raise the window in production, e.g. 900) |
| `MAX_QUESTIONS` | `src/evaluation.py` | 100 | questions per uploaded set |

## API

| Method and path | Auth | Purpose |
|---|---|---|
| `GET /health` | none | status, chunk count, live retrieval mode |
| `POST /ask` | none | `{question}` → `{answer, sources}` |
| `POST /api/admin/login` | none | password; sends a Telegram code, returns `challenge_id` |
| `POST /api/admin/verify-otp` | none | `{challenge_id, code}`; sets the session cookie |
| `POST /api/admin/logout` | none | clears the session |
| `GET /api/admin/session` | session | 200 if signed in as admin, else 401 (the chat page uses it to show admin-only links) |
| `GET` / `POST /api/admin/documents` | session | list / upload one file |
| `DELETE /api/admin/documents/{id}` | session | delete a document everywhere |
| `GET` / `POST /api/admin/eval/datasets` | session | list / upload a question set |
| `GET` / `DELETE /api/admin/eval/datasets/{id}` | session | preview / delete a question set |
| `POST /api/admin/eval/runs` | session | `{dataset_id, modes, retrieval_only, judge}` → starts a run (one at a time) |
| `GET /api/admin/eval/runs` | session | run history |
| `GET /api/admin/eval/runs/{id}` | session | a run's progress and full results |

Interactive docs: `http://localhost:8000/docs`.

**Firestore collections:** `documents`, `chunks` (`<doc id>-<n>`), `eval_datasets`, `eval_runs`.

## Security

| Control | Details |
|---|---|
| Passwords | Argon2id hash in `.env`; wrong usernames take as long as wrong passwords |
| Second factor | 6-digit Telegram code: 5 minutes, single use, 5 attempts, 30-second resend cooldown |
| Sessions | signed JWT, 30 minutes, `HttpOnly` + `SameSite=Strict` cookie (`Secure` on HTTPS) |
| Rate limiting | failed passwords **and** codes count together, per IP |
| Authorisation | every document and evaluation route requires a session |
| Database | Firestore rules deny all direct access; only the backend reads and writes |
| Input | PDF/TXT only, 5 MB; question sets validated row by row; answers sanitised with DOMPurify; user text inserted with `textContent` |
| Secrets | `.env` and the Firebase key are gitignored; Telegram errors never log the bot token |

If a secret is ever committed, **revoke and regenerate it immediately**; deleting the file doesn't remove it from Git history.

## Deployment

The backend serves the frontend, so one Python web service is enough. **Render example:**
- Build: `pip install -r requirements.txt`
- Start: `uvicorn api:app --app-dir src --host 0.0.0.0 --port $PORT`
- Environment: the `.env` values, but use `FIREBASE_CREDENTIALS_JSON` (whole key file) instead of `FIREBASE_KEY_PATH`, paste `ADMIN_PASSWORD_HASH` **without** quotes, and set `COOKIE_SECURE=true`.

Things to know on free tiers:
- Instances sleep and take a while to wake; the chat page says so.
- Every start re-reads all chunks from Firestore, and free Firestore has daily limits, so keep the document set modest.
- Run **one** server process: sign-in codes, rate limits and the "one evaluation at a time" lock live in memory.
- The ranking model is downloaded on first start (~90 MB). If that fails, the server falls back to `hybrid` and logs why.

## Troubleshooting

| Problem | Fix |
|---|---|
| `ModuleNotFoundError` | activate the venv, then `pip install -r requirements.txt` |
| `401 authentication_error` from Claude | check `ANTHROPIC_API_KEY`, and look for a conflicting `ANTHROPIC_AUTH_TOKEN` in your environment |
| Server won't start: "Set ADMIN_USERNAME…" | a variable is missing from `.env` |
| Server won't start: "does not belong to…" | Telegram handle and chat id disagree; run `python src/cli.py link-telegram` |
| No Telegram code arrives | press **Start** in the bot chat; check the token and chat id; look for `Telegram error:` in the terminal |
| Always "Invalid username or password" | the hash is wrong or lost its quotes. Check it with a fresh `hash-password`, and watch for browser autofill |
| "Too many failed attempts" | wait for the rate-limit window, or restart the server locally |
| Logged out at once on the live site | `COOKIE_SECURE=true` without HTTPS |
| Answers say "I don't know" | check `/health` shows chunks, then run an evaluation to see whether retrieval found the evidence |
| "Reranker unavailable" in the log | no internet on first start; the app runs in `hybrid` mode until the model downloads |
| Evaluation says "already running" | only one run at a time; wait, or restart the server (the old run is marked failed) |
| Charts don't appear | the Chart.js CDN is blocked; the tables still work |
| Page looks old after an update | hard refresh with `Ctrl+Shift+R` |

## Known limitations

- Sign-in codes, rate limits and the evaluation lock live in memory, so they need a single server process.
- Telegram chats aren't end-to-end encrypted; an authenticator app (TOTP) would be a stronger second factor.
- One admin account, no roles. Questions are answered independently (no conversation memory).
- Only text-based PDF and TXT files; original files aren't kept, only their text.
- Evaluation checks answers with keywords (plus an optional LLM judge), so a correct answer worded unusually can be marked FAIL. Read the answers when a score drops.

## Roadmap

- [x] RAG pipeline with Chroma and Claude
- [x] Firestore storage, admin upload and delete, polished UI
- [x] Admin sign-in with Argon2, cookie sessions and a Telegram second factor
- [x] Hybrid search (keyword plus vector) with reranking, measured with the evaluation score
- [x] Evaluation dashboard with uploadable question sets, charts and run history
- [ ] GitHub Actions pipeline: lint, unit tests and evaluation on every pull request
- [ ] Streaming answers
- [ ] Source passages shown next to answers
- [ ] Thumbs up/down feedback and a "questions I couldn't answer" view
- [ ] TOTP authenticator option, audit log
- [ ] More file types (DOCX, HTML, URLs) and OCR for scanned PDFs

## Contributing (Git workflow)

Each feature gets its own branch, is tested, then merged through a Pull Request:

```bash
git checkout -b feature/my-feature
git add . && git status     # .env, .venv, chroma_db and the Firebase key must NOT be listed
git commit -m "Describe the change"
git push -u origin feature/my-feature
```

## License

Choose a licence (for example MIT) and add a `LICENSE` file.
