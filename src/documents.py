import io
import os
import uuid

from pypdf import PdfReader

import store
from query import collection, keyword_index

ALLOWED_EXTENSIONS = {".pdf", ".txt"}
MAX_BYTES = 5 * 1024 * 1024   # 5 MB
CHUNK_WORDS = 400             # words per chunk
OVERLAP_WORDS = 50            # words shared by neighbouring chunks, so no sentence is lost at a cut


def chunk_text(text: str) -> list[str]:
    """Split text into overlapping chunks of roughly CHUNK_WORDS words."""
    words = text.split()
    step = CHUNK_WORDS - OVERLAP_WORDS
    return [" ".join(words[start:start + CHUNK_WORDS]) for start in range(0, len(words), step)]


def extract_text(filename: str, data: bytes) -> str:
    if filename.lower().endswith(".pdf"):
        reader = PdfReader(io.BytesIO(data))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    return data.decode("utf-8", errors="ignore")


def _index(doc_id: str, filename: str, chunks: list[str]):
    collection.upsert(
        documents=chunks,
        ids=[f"{doc_id}-{i}" for i in range(len(chunks))],
        metadatas=[{"doc_id": doc_id, "source": filename, "chunk": i} for i in range(len(chunks))],
    )
    keyword_index.invalidate()


def add_document(filename: str, data: bytes) -> dict:
    filename = os.path.basename(filename)
    if os.path.splitext(filename)[1].lower() not in ALLOWED_EXTENSIONS:
        raise ValueError("Only .pdf and .txt files are allowed")

    try:
        text = extract_text(filename, data)
    except Exception:
        raise ValueError("Could not read that file. Is it a valid PDF or text file?")
    chunks = chunk_text(text)
    if not chunks:
        raise ValueError("No text could be extracted (scanned PDFs need OCR first)")

    doc_id = uuid.uuid4().hex
    store.save_document(doc_id, filename, len(data), chunks)
    try:
        _index(doc_id, filename, chunks)
    except Exception:
        store.delete_document(doc_id)   # don't leave Firestore and Chroma out of sync
        raise
    return {"id": doc_id, "filename": filename, "chunk_count": len(chunks)}


def remove_document(doc_id: str) -> bool:
    found = store.delete_document(doc_id)
    collection.delete(where={"doc_id": doc_id})
    keyword_index.invalidate()
    return found


def rebuild_index() -> int:
    """Make Chroma match Firestore exactly. Runs at every server start."""
    existing = collection.get()["ids"]
    if existing:
        collection.delete(ids=existing)

    ids, texts, metas = [], [], []
    for chunk_id, c in store.all_chunks():
        ids.append(chunk_id)
        texts.append(c["text"])
        metas.append({"doc_id": c["doc_id"], "source": c["source"], "chunk": c["chunk"]})

    for i in range(0, len(ids), 500):
        collection.upsert(ids=ids[i:i + 500], documents=texts[i:i + 500], metadatas=metas[i:i + 500])
    keyword_index.invalidate()
    return len(ids)