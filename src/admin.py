import os

from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile
from pydantic import BaseModel, Field

import auth
import documents
import store

# Public routes: login and logout only
public = APIRouter(prefix="/api/admin", tags=["admin-auth"])

# Protected routes: every route here requires a valid session cookie
router = APIRouter(
    prefix="/api/admin", tags=["admin"], dependencies=[Depends(auth.require_admin)]
)


class Login(BaseModel):
    username: str = Field(max_length=100)
    password: str = Field(max_length=200)


@public.post("/login")
def login(body: Login, request: Request, response: Response):
    auth.check_rate_limit(request)
    if not auth.check_credentials(body.username, body.password):
        auth.record_failure(request)
        raise HTTPException(401, "Invalid username or password")
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