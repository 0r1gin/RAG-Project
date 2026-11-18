# doc-chat: Chat With Your Documents

A Retrieval-Augmented Generation (RAG) web app. An admin uploads PDF and text files through a protected panel, the app splits them into passages and indexes them, and visitors ask questions in a chat page. Claude answers using only the retrieved passages and names the sources it used.

> **Live demo:** _add your link here_  ·  **Screenshots:** _add `docs/chat.png` and `docs/admin.png`_

---

## Features

**Chat**
- Question answering grounded in your documents, with source names
- Markdown-formatted answers, sanitised before display
- Suggestion chips, copy button, retry on error, light and dark mode
- Status indicator that also wakes a sleeping free-tier server

**Admin panel**
- Drag-and-drop **multi-file upload** (up to 20 files at once, uploaded one at a time with per-file results)
- Document list with search, stats (documents, chunks, total size) and a delete confirmation dialog
- Deleting a document removes it from both the database **and** the search index

**Storage**
- Firestore is the source of truth for documents and chunks
- The Chroma search index is rebuilt from Firestore at every server start, so free hosts that wipe their disk lose nothing

**Security**
- Password login with Argon2 hashing
- Telegram bot one-time code as a second factor, sent to an account the backend determines
- Short-lived signed session in an `HttpOnly`, `SameSite=Strict` cookie
- Rate limiting, constant-time comparisons, input validation, no secrets in the repository

**Quality**
- Evaluation harness with synonym groups, priorities, forbidden phrases, contradiction checks and an optional LLM judge

---

## Architecture

```
                         ┌──────────────────────────────────────────────┐
 Browser                 │  FastAPI backend (src/)                      │
 ├─ chat page      ───►  │  POST /ask ──► Chroma (top 3 chunks) ──► Claude
 ├─ admin page     ───►  │  /api/admin/* (cookie required)              │
 └─ login page     ───►  │      ├─ upload ─► extract ─► chunk ─┬─► Firestore (source of truth)
                         │      └─ delete ───────────────────  └─► Chroma    (search index)
                         │  login ─► Argon2 ─► Telegram OTP ─► session cookie
                         └──────────────────────────────────────────────┘
                                      ▲
                       server start: Firestore ─► rebuild Chroma
```

**Why this design**

| Decision | Reason |
|---|---|
| Firestore holds the data, Chroma is a rebuildable cache | Free hosts have ephemeral disks. Rebuilding on start keeps the app stateless |
| Firestore only, no Cloud Storage | Cloud Storage for Firebase needs the paid Blaze plan; the app only needs the extracted text |
| FastAPI serves the frontend itself | One deployment, no CORS setup, no separate static host |
| Plain HTML, CSS and JavaScript with Pico CSS | No build step; everything is editable directly |
| Files uploaded one at a time from the browser | Each file gets its own result, one bad PDF doesn't sink a batch, and requests stay short for free hosts |

---

## Tech stack

| Layer | Tools |
|---|---|
| Backend | Python 3.10+, FastAPI, Uvicorn |
| Retrieval | ChromaDB (local embeddings), pypdf |
| LLM | Anthropic Claude API |
| Database | Firebase Firestore (Admin SDK) |
| Auth | argon2-cffi, PyJWT, Telegram Bot API (via httpx) |
| Frontend | HTML, CSS, vanilla JavaScript, Pico CSS, marked, DOMPurify |
| Testing | Custom evaluation harness (`tests/eval.py`) |

---

## Project structure

```
doc-chat/
├── README.md
├── requirements.txt
├── .env                      # secrets (never committed)
├── .gitignore
├── serviceAccountKey.json    # Firebase key (never committed)
├── data/                     # optional local seed documents
├── chroma_db/                # generated search index (never committed)
├── frontend/
│   ├── index.html, app.js    # chat page
│   ├── admin.html, admin.js  # admin panel
│   ├── login.html, login.js  # two-step login
│   ├── common.js             # theme toggle, toasts, helpers
│   └── style.css             # theme and layout (edit the variables at the top)
├── src/
│   ├── api.py                # app setup, /ask, /health, serves frontend
│   ├── query.py              # retrieve chunks, ask Claude
│   ├── ingest.py             # chunking helpers (and a local-folder ingest script)
│   ├── documents.py          # add, remove and rebuild documents
│   ├── store.py              # all Firestore reads and writes
│   ├── admin.py              # admin API routes
│   ├── auth.py               # password check, session cookie, rate limiting
│   ├── otp.py                # Telegram one-time codes
│   ├── make_hash.py          # generates the admin password hash
│   ├── link_telegram.py      # one-time Telegram chat-id lookup
│   └── migrate_local.py      # optional: upload data/ files to Firestore
└── tests/
    └── eval.py               # scored evaluation questions
```

---

## Setup

### Prerequisites

- Python 3.10 or newer, and Git
- An Anthropic API key (console.anthropic.com)
- A Firebase project on the free Spark plan (console.firebase.google.com)
- A Telegram account **with a public username** (Settings → Username)

### 1. Clone and create a virtual environment

```bash
git clone https://github.com/YOUR-USERNAME/doc-chat.git
cd doc-chat
python -m venv .venv
```

| Shell | Activate |
|---|---|
| Windows cmd | `.venv\Scripts\activate.bat` |
| Windows PowerShell | `.venv\Scripts\Activate.ps1` |
| macOS / Linux | `source .venv/bin/activate` |

> PowerShell "scripts disabled" error? Run `Set-ExecutionPolicy -Scope Process Bypass`, then activate again.

```bash
pip install -r requirements.txt
```

### 2. Set up Firebase

1. Create a project, then **Build → Firestore Database → Create database** (production mode).
2. Under **Rules**, block all direct access and publish. Only the backend (Admin SDK, which bypasses rules) touches the database:
   ```
   rules_version = '2';
   service cloud.firestore {
     match /databases/{database}/documents {
       match /{document=**} {
         allow read, write: if false;
       }
     }
   }
   ```
3. **Project settings → Service accounts → Generate new private key.** Save the file as `serviceAccountKey.json` in the project root.

### 3. Generate the admin password hash and session secret

```bash
python src/make_hash.py
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

### 4. Create the Telegram bot

1. In Telegram, message **@BotFather**, send `/newbot`, and copy the token.
2. Open your new bot and press **Start**. A bot cannot message anyone who hasn't done this.
3. Fill in `.env` (next step), then run the link script once:
   ```bash
   python src/link_telegram.py
   ```
   It prints a `TELEGRAM_ADMIN_CHAT_ID=...` line. Add it to `.env`.

Why a script: Telegram bots can only message a numeric chat ID, not a `@handle`. The script finds the chat ID of whoever started the bot using the handle you configured, and the server re-checks at every start that the ID still belongs to that handle.

### 5. Create `.env`

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

Keep the single quotes around the hash locally (it contains `$` characters). No spaces around `=`.

| Variable | Purpose |
|---|---|
| `ANTHROPIC_API_KEY` | Claude API access |
| `FIREBASE_KEY_PATH` | Path to the service-account file (local development) |
| `FIREBASE_CREDENTIALS_JSON` | Full contents of that file (use this on a host instead of the path) |
| `ADMIN_USERNAME` | Admin login name |
| `ADMIN_PASSWORD_HASH` | Argon2 hash from `make_hash.py` |
| `JWT_SECRET` | Signs session tokens; 32+ characters |
| `COOKIE_SECURE` | `true` on HTTPS hosts, `false` on `http://localhost` |
| `TELEGRAM_BOT_TOKEN` | Bot token from BotFather |
| `ADMIN_TELEGRAM_HANDLE` | The admin's Telegram username, without `@` |
| `TELEGRAM_ADMIN_CHAT_ID` | Numeric chat ID from `link_telegram.py` |

The server refuses to start if any required admin or Telegram setting is missing, or if the chat ID no longer matches the handle.

### 6. Run it

```bash
uvicorn api:app --app-dir src --reload --port 8000
```

Restart after changing `.env`, because `--reload` only watches Python files.

| URL | What |
|---|---|
| `http://localhost:8000/` | Chat page |
| `http://localhost:8000/login.html` | Admin login |
| `http://localhost:8000/admin.html` | Admin panel (requires login) |
| `http://localhost:8000/docs` | Interactive API documentation |
| `http://localhost:8000/health` | Status and indexed chunk count |

**Optional:** upload files you already have in `data/` to Firestore once (running it twice creates duplicates):

```bash
python src/migrate_local.py
```

---

## Usage

### Asking questions

Open the chat page, click a suggestion or type a question, and press Enter (Shift+Enter for a new line). Each question is answered on its own, with no memory of earlier ones. If the passages don't contain the answer, the app says so instead of guessing.

### Managing documents

1. Go to `/login.html`, enter your username and password, then the 6-digit code that arrives in Telegram.
2. On the admin page, drop files onto the upload area or click to choose them. PDF and TXT only, up to 5 MB each, up to 20 per batch. Each file shows its own progress and result. Duplicates by name are skipped, so delete the old one first to replace it.
3. Use **Delete** on any row to remove the document, its stored chunks and its search entries.
4. Sessions last 30 minutes. **Log out** ends one immediately.

Scanned PDFs without a text layer can't be indexed (they would need OCR first).

### Local seed files

`src/ingest.py` also still works as a script that indexes the `data/` folder straight into the local Chroma database. It's handy for quick experiments, but the web app's source of truth is Firestore.

---

## How it works

**Ingestion**
1. The uploaded file is read in memory and its text is extracted (`pypdf` for PDFs).
2. The text is split into overlapping chunks of about 400 words.
3. The chunks are written to Firestore in batches, then the document's metadata is written last, so a failed upload never appears in the list.
4. The chunks are added to Chroma, which creates embeddings. If that step fails, the Firestore write is rolled back.

**Question answering**
1. Chroma returns the 3 chunks closest in meaning to the question.
2. Claude receives those chunks and the question with the instruction to answer only from them and to say so when the answer isn't there.
3. The answer and the source file names go back to the browser.

**Firestore data model**

| Collection | Document id | Fields |
|---|---|---|
| `documents` | random id | `filename`, `size_bytes`, `chunk_count`, `uploaded_at` |
| `chunks` | `<doc id>-<n>` | `doc_id`, `source`, `chunk`, `text` |

**Startup:** the Chroma collection is emptied and refilled from `chunks`, so the index always matches Firestore.

### API reference

| Method and path | Auth | Purpose |
|---|---|---|
| `GET /health` | none | Status and chunk count |
| `POST /ask` | none | `{question}` returns `{answer, sources}` (3 to 500 characters) |
| `POST /api/admin/login` | none | Password check; sends a code to Telegram and returns a `challenge_id` |
| `POST /api/admin/verify-otp` | none | `{challenge_id, code}`; sets the session cookie on success |
| `POST /api/admin/logout` | none | Clears the session cookie |
| `GET /api/admin/documents` | cookie | List documents |
| `POST /api/admin/documents` | cookie | Upload one file (multipart) |
| `DELETE /api/admin/documents/{id}` | cookie | Delete a document everywhere |

---

## Security

| Control | Details |
|---|---|
| Password storage | Argon2id hash in an environment variable, never plain text. Wrong usernames take similar time to wrong passwords |
| Second factor | 6-digit code via Telegram, valid for 5 minutes, single use, 5 attempts, 30 second resend cooldown |
| Sessions | Signed JWT, 30 minute expiry, `HttpOnly` + `SameSite=Strict` cookie (`Secure` on HTTPS) |
| Rate limiting | 5 failed attempts per IP in 15 minutes, counted across passwords **and** codes |
| Authorisation | Every document route depends on a session check; a correct password alone grants nothing |
| Database | Firestore rules deny all direct access; only the backend can read or write |
| Input handling | Uploads limited to PDF/TXT and 5 MB, file names stripped to a base name, question length capped, answers sanitised with DOMPurify, file names inserted with `textContent` |
| Secrets | `.env` and the Firebase key are gitignored. Telegram errors are rewritten so the bot token never reaches the logs |

If a secret is ever committed, **revoke and regenerate it immediately**. Deleting the file later does not remove it from Git history.

---

## Configuration

| Setting | Where | Default | Effect |
|---|---|---|---|
| `CHUNK_WORDS` / `OVERLAP_WORDS` | `src/ingest.py` | 400 / 50 | Chunk size and overlap |
| `N_RESULTS` | `src/query.py` | 3 | Chunks retrieved per question |
| `MODEL` | `src/query.py` | `claude-sonnet-5-5` | Claude model; check current names at docs.claude.com |
| `max_tokens` | `src/query.py` | 3000 | Answer limit (thinking tokens count toward it) |
| `MAX_BYTES` | `src/documents.py` | 5 MB | Per-file upload limit (keep `admin.js` in sync) |
| `MAX_FILES`, `MAX_BYTES` | `frontend/admin.js` | 20, 5 MB | Batch limits in the browser |
| `TOKEN_MINUTES` | `src/auth.py` | 30 | Session length |
| `MAX_FAILURES`, `WINDOW_SECONDS` | `src/auth.py` | 5, 900 | Login rate limit |
| `OTP_TTL_SECONDS`, `MAX_ATTEMPTS`, `RESEND_COOLDOWN_SECONDS` | `src/otp.py` | 300, 5, 30 | One-time code rules |
| `SUGGESTIONS` | `frontend/app.js` | sample questions | Chips on the chat page |
| Accent colours | top of `frontend/style.css` | indigo | Site-wide theme |

After changing chunk settings, re-upload your documents so existing chunks are rebuilt with the new size.

---

## Evaluation

`tests/eval.py` runs a list of questions through the real pipeline and scores each answer.

| Option | Effect |
|---|---|
| `keywords` | Strings, or lists of synonyms (`["2", "two"]`), matched as whole words |
| `match` | `all` keywords required, `any` one is enough |
| `min_matches` | At least N keywords (for "name a few" questions) |
| `priority` | `critical` (3 points), `high` (2), `normal` (1), giving a weighted score |
| `forbidden` | Phrases that mark an answer wrong, such as "I don't know" |
| `patterns` | Regexes the answer must match |
| `stance` | `affirm` or `negate`; flags answers that contain the keywords but say the opposite |
| `reference` | Plain-English correct answer, used by the optional LLM judge |
| `JUDGE_MODE = "on_pass"` | Has Claude double-check passing answers for meaning |

Statuses: `PASS`, `FAIL` (keywords missing) and `CONFLICT` (keywords present but the meaning looks wrong). A failing `critical` test makes the script exit with a non-zero code, ready for CI.

```bash
python tests/eval.py
```

The evaluation reads the **local** Chroma index. Start the server once first (it rebuilds the index from Firestore), or add `import documents; documents.rebuild_index()` at the top of `eval.py`.

### Results log

| Date | Chunk words | Results | Weighted score | Notes |
|---|---|---|---|---|
| YYYY-MM-DD | 400 | 3 | _/_ | baseline |

---

## Deployment

The backend serves the frontend, so one free Python web service is enough.

**Render example**
- Build command: `pip install -r requirements.txt`
- Start command: `uvicorn api:app --app-dir src --host 0.0.0.0 --port $PORT`
- Environment variables: the table above, with these differences:
  - Use `FIREBASE_CREDENTIALS_JSON` (the whole key file) instead of `FIREBASE_KEY_PATH`
  - Paste `ADMIN_PASSWORD_HASH` raw, with no quotes
  - Set `COOKIE_SECURE=true`

**Free-tier realities**
- Free instances sleep after inactivity and take a while to wake. The chat page shows a "server may be waking up" message and pings `/health` on load.
- Every start re-reads all chunks from Firestore. Free Firestore has daily read, write and storage limits (check Firebase's current pricing page), so keep the document set modest.
- Run a **single** server process. One-time-code and rate-limit state is kept in memory.

After deploying, test the live site end to end: ask a question, log in with a code, upload a document, delete it. If the session doesn't stick, check `COOKIE_SECURE` and that the site is served over HTTPS.

---

## Git workflow

`main` holds the last working version. Each feature is built on its own branch, tested, then merged through a Pull Request.

| Branch | Adds |
|---|---|
| `feature/web-ui` | FastAPI backend and the first Pico CSS frontend |
| `feature/firebase-storage` | Firestore storage, admin upload and delete |
| `feature/ui-polish` | Redesigned chat and admin pages, multi-file upload |
| `feature/admin-auth` | Admin login with Argon2 and cookie sessions |
| `feature/telegram-otp` | Telegram one-time code as a second factor |

**Starting a feature**

```bash
git checkout main
git pull
git checkout -b feature/my-feature
# ...work...
git add .
git status            # .env, .venv, chroma_db and serviceAccountKey.json must NOT be listed
git commit -m "Describe the change"
git push -u origin feature/my-feature
```

Then open a Pull Request, review **Files changed** for secrets, merge, and clean up:

```bash
git checkout main
git pull
git branch -d feature/my-feature
git tag v0.4-my-feature && git push origin v0.4-my-feature
```

**Useful commands**

| Task | Command |
|---|---|
| History as a graph | `git log --oneline --graph --all` |
| Which branches contain a file's history | `git log --all --oneline -- path/to/file` |
| Save a bookmark before risky work | `git branch backup/before-cleanup` |
| Stash unfinished work | `git stash`, later `git stash pop` |
| Cancel a merge in progress | `git merge --abort` |
| During a merge, take the incoming side of a file | `git checkout MERGE_HEAD -- path` |
| Compare with a backup branch | `git diff backup/before-cleanup -- frontend` |

**Shell differences on Windows:** `Select-String` exists only in PowerShell; in cmd use `findstr /C:"text" file`. `git`, `python`, `pip` and `uvicorn` behave identically in both.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `python` not found | Use `python3`, or reinstall with "Add to PATH" ticked |
| `(.venv)` missing from the prompt | Re-run the activate command |
| `ModuleNotFoundError` | Activate the venv, then `pip install -r requirements.txt` |
| `401 authentication_error` from Claude | Check `ANTHROPIC_API_KEY`; also look for a conflicting `ANTHROPIC_AUTH_TOKEN` or stale variable in your system environment |
| `'ThinkingBlock' has no attribute 'text'` | Join only blocks where `block.type == "text"` (already done in `query.py`) |
| `Directory '...\frontend' does not exist` | Create the `frontend/` folder with its files, and start Uvicorn from the project root |
| Server won't start: "Set ADMIN_USERNAME…" | A variable is missing from `.env` |
| Server won't start: "does not belong to…" | The Telegram handle and chat ID disagree; re-run `src/link_telegram.py` |
| No Telegram code arrives | Press **Start** in the bot chat; check the token and chat ID; look for a `Telegram error:` line in the terminal |
| `link_telegram.py` finds nothing | Send the bot a fresh message, run it again, and check your public Telegram username matches `.env` |
| "Please wait 30 seconds" | Resend cooldown; wait, or restart the server while testing |
| `429 Too many failed attempts` | Per-IP limit; restart locally, or wait 15 minutes |
| Always "Invalid username or password" | The hash was truncated, or lost its single quotes in a local `.env` |
| Logged out immediately on the live site | `COOKIE_SECURE=true` on plain `http://`, or the site isn't on HTTPS |
| Codes work locally but fail when deployed | The host runs several workers or instances; use one process |
| Empty answers from a PDF | It's probably scanned images; OCR it first |
| Answers say "I don't know" | Check `/health` for a non-zero chunk count, then try `N_RESULTS = 5` or smaller chunks |
| Page looks unstyled or old | Hard refresh (`Ctrl+Shift+R`); check the Pico CDN link loads |

---

## Known limitations

- One-time-code and rate-limit state live in memory, so they require a single server process. A restart between the password and the code invalidates the code.
- Telegram bot chats are not end-to-end encrypted. This is a solid second factor, but an authenticator-app code (TOTP) would be stronger.
- The rate limit is per IP; behind several proxies the address read from `X-Forwarded-For` may be a proxy's.
- There is a single admin account and no roles.
- Questions are answered independently; there is no conversation memory.
- Only text-based PDF and TXT files are supported.
- Original files are not kept, only the extracted text.

---

## Roadmap

- [x] RAG pipeline with Chroma and Claude
- [x] Evaluation harness with priorities, synonyms and contradiction checks
- [x] FastAPI backend and web frontend
- [x] Firestore storage with admin upload and delete
- [x] Multi-file upload and polished UI
- [x] Admin login with Argon2 and cookie sessions
- [x] Telegram one-time-code second factor
- [ ] Streaming answers (Server-Sent Events)
- [ ] Hybrid search (keyword plus vector) with reranking, measured with the eval score
- [ ] GitHub Actions pipeline that fails when the eval score drops
- [ ] Source passages shown and highlighted next to answers
- [ ] Thumbs up/down feedback and a "questions I couldn't answer" admin view
- [ ] Audit log of admin actions
- [ ] TOTP authenticator option
- [ ] Docker setup and automated tests with mocked Firestore and Claude
- [ ] More file types (DOCX, HTML, web URLs) and OCR for scanned PDFs

---

## License

Choose a licence (for example MIT) and add a `LICENSE` file.