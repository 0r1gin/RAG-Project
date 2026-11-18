import os

from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile
from pydantic import BaseModel, Field

import auth
import documents
import otp
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