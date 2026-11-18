import os

from fastapi import APIRouter, File, HTTPException, UploadFile

import documents
import store

router = APIRouter(prefix="/api/admin", tags=["admin"])


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