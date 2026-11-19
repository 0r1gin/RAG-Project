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


# ---------------- evaluation ----------------
# Firestore can't hold a list inside a list (keyword synonym groups are exactly that),
# so questions and per-question results are stored as JSON text.
def _iso(data: dict, *fields):
    for f in fields:
        if data.get(f) is not None:
            data[f] = data[f].isoformat()
    return data


def save_dataset(name: str, questions: list[dict]) -> str:
    ref = db.collection("eval_datasets").document()
    ref.set({
        "name": name,
        "count": len(questions),
        "questions_json": json.dumps(questions),
        "created_at": datetime.now(timezone.utc),
    })
    return ref.id


def list_datasets() -> list[dict]:
    query = (db.collection("eval_datasets")
             .order_by("created_at", direction=firestore.Query.DESCENDING)
             .select(["name", "count", "created_at"]))
    return [_iso({"id": d.id, **d.to_dict()}, "created_at") for d in query.stream()]


def get_dataset(dataset_id: str):
    snap = db.collection("eval_datasets").document(dataset_id).get()
    if not snap.exists:
        return None
    data = snap.to_dict()
    return {"id": snap.id, "name": data["name"], "questions": json.loads(data["questions_json"])}


def delete_dataset(dataset_id: str) -> bool:
    ref = db.collection("eval_datasets").document(dataset_id)
    if not ref.get().exists:
        return False
    ref.delete()
    return True


def create_run(fields: dict) -> str:
    ref = db.collection("eval_runs").document()
    ref.set({**fields, "started_at": datetime.now(timezone.utc)})
    return ref.id


def update_run(run_id: str, fields: dict):
    if "results" in fields:
        fields = {**fields, "results_json": json.dumps(fields.pop("results"))}
    if fields.get("status") in ("done", "failed"):
        fields["finished_at"] = datetime.now(timezone.utc)
    db.collection("eval_runs").document(run_id).update(fields)


RUN_LIST_FIELDS = ["dataset_name", "modes", "production_mode", "retrieval_only", "judge",
                   "status", "done", "total", "summaries", "warning", "error",
                   "started_at", "finished_at"]


def list_runs(limit: int = 50) -> list[dict]:
    query = (db.collection("eval_runs")
             .order_by("started_at", direction=firestore.Query.DESCENDING)
             .limit(limit)
             .select(RUN_LIST_FIELDS))           # leave out the large results_json
    return [_iso({"id": d.id, **d.to_dict()}, "started_at", "finished_at") for d in query.stream()]


def get_run(run_id: str):
    snap = db.collection("eval_runs").document(run_id).get()
    if not snap.exists:
        return None
    data = snap.to_dict()
    data["results"] = json.loads(data.pop("results_json", "{}") or "{}")
    return _iso({"id": snap.id, **data}, "started_at", "finished_at")


def mark_interrupted_runs() -> int:
    """Runs still 'running' at startup died with the previous server process."""
    stuck = list(db.collection("eval_runs").where(filter=FieldFilter("status", "==", "running")).stream())
    for d in stuck:
        d.reference.update({"status": "failed", "error": "Interrupted: the server restarted during the run",
                            "finished_at": datetime.now(timezone.utc)})
    return len(stuck)