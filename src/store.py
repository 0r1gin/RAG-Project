"""Firestore access. Firestore is the source of truth; Chroma is a rebuildable index."""
import json
import os
from datetime import datetime, timezone

import firebase_admin
from dotenv import load_dotenv
from firebase_admin import credentials, firestore
from google.cloud.firestore_v1.base_query import FieldFilter

load_dotenv()


def _init_app():
    try:
        return firebase_admin.get_app()
    except ValueError:
        raw = os.getenv("FIREBASE_CREDENTIALS_JSON")   # used on the host
        if raw:
            cred = credentials.Certificate(json.loads(raw))
        else:                                           # used locally
            cred = credentials.Certificate(os.getenv("FIREBASE_KEY_PATH", "firestoreAccountKey.json"))
        return firebase_admin.initialize_app(cred)


_init_app()
db = firestore.client()

BATCH_SIZE = 400   # Firestore allows 500 operations per batch


def _write_in_batches(items, apply):
    batch = db.batch()
    count = 0
    for item in items:
        apply(batch, item)
        count += 1
        if count == BATCH_SIZE:
            batch.commit()
            batch = db.batch()
            count = 0
    if count:
        batch.commit()


def save_document(doc_id: str, filename: str, size_bytes: int, chunks: list[str]):
    def put(batch, pair):
        i, text = pair
        ref = db.collection("chunks").document(f"{doc_id}-{i}")
        batch.set(ref, {"doc_id": doc_id, "source": filename, "chunk": i, "text": text})

    _write_in_batches(list(enumerate(chunks)), put)
    # Metadata last, so a failed upload never shows up in the document list.
    db.collection("documents").document(doc_id).set({
        "filename": filename,
        "size_bytes": size_bytes,
        "chunk_count": len(chunks),
        "uploaded_at": datetime.now(timezone.utc),
    })


def list_documents() -> list[dict]:
    query = db.collection("documents").order_by("uploaded_at", direction=firestore.Query.DESCENDING)
    out = []
    for d in query.stream():
        data = d.to_dict()
        data["id"] = d.id
        data["uploaded_at"] = data["uploaded_at"].isoformat()
        out.append(data)
    return out


def delete_document(doc_id: str) -> bool:
    doc_ref = db.collection("documents").document(doc_id)
    existed = doc_ref.get().exists
    chunk_refs = [
        d.reference
        for d in db.collection("chunks").where(filter=FieldFilter("doc_id", "==", doc_id)).stream()
    ]
    _write_in_batches(chunk_refs, lambda batch, ref: batch.delete(ref))
    doc_ref.delete()
    return existed or bool(chunk_refs)


def all_chunks():
    """Yields (chunk_id, data) for every stored chunk."""
    for d in db.collection("chunks").stream():
        yield d.id, d.to_dict()