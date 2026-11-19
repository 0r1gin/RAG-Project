import os
import threading

from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile
from pydantic import BaseModel, Field

import auth
import documents
import evaluation
import otp
import query
import store

public = APIRouter(prefix="/api/admin", tags=["admin-auth"])

router = APIRouter(
    prefix="/api/admin", tags=["admin"], dependencies=[Depends(auth.require_admin)]
)


class Login(BaseModel):
    username: str = Field(max_length=100)
    password: str = Field(max_length=200)


class OtpBody(BaseModel):
    challenge_id: str = Field(max_length=100)
    code: str = Field(pattern=r"^[0-9]{6}$")    # [0-9], not \d, which also matches non-ASCII digits


@public.post("/login")
def login(body: Login, request: Request):
    """Step 1: password. On success a code is sent to Telegram. No session yet."""
    auth.check_rate_limit(request)
    if not auth.check_credentials(body.username, body.password):
        auth.record_failure(request)
        raise HTTPException(401, "Invalid username or password")
    # Failures are NOT cleared here: the OTP step must still pass.
    try:
        challenge_id = otp.start_challenge()
    except otp.OtpCooldown:
        raise HTTPException(429, "Please wait 30 seconds before requesting another code")
    except RuntimeError:
        raise HTTPException(502, "Could not send the verification code")
    return {"otp_required": True, "challenge_id": challenge_id}


@public.post("/verify-otp")
def verify_otp(body: OtpBody, request: Request, response: Response):
    """Step 2: the Telegram code. Only now is the session cookie issued."""
    auth.check_rate_limit(request)
    if not otp.verify_challenge(body.challenge_id, body.code):
        auth.record_failure(request)
        raise HTTPException(401, "Invalid or expired code")
    auth.clear_failures(request)
    auth.issue_token(response)
    return {"ok": True}


@public.post("/logout")
def logout(response: Response):
    response.delete_cookie(auth.COOKIE_NAME, path="/")
    return {"ok": True}


@router.get("/session")
def session():
    """200 if the visitor has a valid admin session (the router's auth check), 401 otherwise."""
    return {"admin": True}


@router.get("/documents")
def list_documents():
    return store.list_documents()


@router.post("/documents")
def upload_document(file: UploadFile = File(...)):
    data = file.file.read(documents.MAX_BYTES + 1)
    if len(data) > documents.MAX_BYTES:
        raise HTTPException(413, "File too large (max 5 MB)")
    try:
        return documents.add_document(os.path.basename(file.filename or "upload"), data)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.delete("/documents/{doc_id}")
def delete_document(doc_id: str):
    if not documents.remove_document(doc_id):
        raise HTTPException(404, "Document not found")
    return {"deleted": doc_id}


# ================= EVALUATION =================
DEFAULT_ID = "default"
_run_lock = threading.Lock()     # one evaluation at a time: runs are slow and call Claude


def _load_questions(dataset_id: str) -> tuple[str, list[dict]]:
    if dataset_id == DEFAULT_ID:
        return "Default questions", evaluation.load_default_set()
    data = store.get_dataset(dataset_id)
    if not data:
        raise HTTPException(404, "Question set not found")
    return data["name"], data["questions"]


@router.get("/eval/datasets")
def list_datasets():
    default = {"id": DEFAULT_ID, "name": "Default questions", "builtin": True,
               "count": len(evaluation.load_default_set()), "created_at": None}
    return [default] + store.list_datasets()


@router.get("/eval/datasets/{dataset_id}")
def get_dataset(dataset_id: str):
    name, questions = _load_questions(dataset_id)
    return {"id": dataset_id, "name": name, "questions": questions}


@router.post("/eval/datasets")
def upload_dataset(file: UploadFile = File(...)):
    data = file.file.read(evaluation.MAX_FILE_BYTES + 1)
    name = os.path.basename(file.filename or "questions")
    try:
        questions = evaluation.parse_dataset(name, data)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"id": store.save_dataset(name, questions), "name": name, "count": len(questions)}


@router.delete("/eval/datasets/{dataset_id}")
def delete_dataset(dataset_id: str):
    if dataset_id == DEFAULT_ID:
        raise HTTPException(400, "The default set lives in tests/questions.json and can't be deleted here")
    if not store.delete_dataset(dataset_id):
        raise HTTPException(404, "Question set not found")
    return {"deleted": dataset_id}


class RunRequest(BaseModel):
    dataset_id: str = Field(max_length=100)
    modes: list[str] = Field(min_length=1, max_length=len(query.RETRIEVAL_MODES))
    retrieval_only: bool = False
    judge: bool = False


def _execute_run(run_id: str, questions: list[dict], modes: list[str], body: RunRequest):
    try:
        last = {"saved": 0}

        def progress(done, total):
            if done - last["saved"] >= 3 or done == total:   # don't write to Firestore every question
                store.update_run(run_id, {"done": done})
                last["saved"] = done

        out = evaluation.run_set(questions, modes, body.retrieval_only, body.judge, progress)
        store.update_run(run_id, {"status": "done", **out})
    except Exception as e:
        store.update_run(run_id, {"status": "failed", "error": str(e)[:500]})
    finally:
        _run_lock.release()


@router.post("/eval/runs")
def start_run(body: RunRequest):
    unknown = [m for m in body.modes if m not in query.RETRIEVAL_MODES]
    if unknown:
        raise HTTPException(400, f"Unknown mode(s): {', '.join(unknown)}")
    if body.retrieval_only and body.judge:
        raise HTTPException(400, "The judge needs answers; turn off 'retrieval only' to use it")
    if not _run_lock.acquire(blocking=False):
        raise HTTPException(409, "An evaluation is already running. Wait for it to finish.")
    try:
        name, questions = _load_questions(body.dataset_id)
        modes, warning = evaluation.usable_modes(list(dict.fromkeys(body.modes)))
        if not modes:
            raise HTTPException(503, warning)
        run_id = store.create_run({
            "dataset_id": body.dataset_id, "dataset_name": name, "modes": modes,
            "production_mode": query.active_mode, "retrieval_only": body.retrieval_only,
            "judge": body.judge, "status": "running", "done": 0,
            "total": len(questions) * len(modes), "warning": warning, "summaries": {},
        })
    except BaseException:
        _run_lock.release()
        raise
    threading.Thread(target=_execute_run, args=(run_id, questions, modes, body), daemon=True).start()
    return {"id": run_id, "warning": warning}


@router.get("/eval/runs")
def list_runs():
    return store.list_runs()


@router.get("/eval/runs/{run_id}")
def get_run(run_id: str):
    run = store.get_run(run_id)
    if not run:
        raise HTTPException(404, "Run not found")
    return run