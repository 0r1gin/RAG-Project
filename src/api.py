from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import admin
import otp
import documents
import query
import store
from query import answer_with_sources, collection

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"


@asynccontextmanager
async def lifespan(app: FastAPI):
    otp.verify_link()                      # refuse to start if the chat id doesn't match the handle
    count = documents.rebuild_index()      # Firestore → Chroma
    print(f"Index rebuilt from Firestore: {count} chunks")
    if query.active_mode.endswith("+rerank"):
        try:
            query.reranker.load()              # first start downloads the model (~80 MB)
        except Exception as e:                 # no network, disk full, ...: still serve answers
            query.active_mode = query.active_mode.replace("+rerank", "")
            print(f"Reranker unavailable ({e}); falling back to '{query.active_mode}' retrieval")
    print(f"Retrieval mode: {query.active_mode}")
    stuck = store.mark_interrupted_runs()   # evaluations cut off by the last shutdown
    if stuck:
        print(f"Marked {stuck} interrupted evaluation run(s) as failed")
    yield


app = FastAPI(lifespan=lifespan)
app.include_router(admin.public)
app.include_router(admin.router)


@app.middleware("http")
async def no_stale_pages(request, call_next):
    """Make browsers re-check the HTML/JS/CSS on every load (a cheap 304 when unchanged).
    Without this they may reuse an old copy for hours after an update."""
    response = await call_next(request)
    if not request.url.path.startswith(("/api/", "/ask", "/health", "/docs", "/openapi")):
        response.headers["Cache-Control"] = "no-cache"
    return response


class Question(BaseModel):
    question: str = Field(min_length=3, max_length=500)


@app.get("/health")
def health():
    return {"ok": True, "chunks": collection.count(), "retrieval": query.active_mode}


@app.post("/ask")
def ask(body: Question):
    text, sources = answer_with_sources(body.question)
    return {"answer": text, "sources": sources}


# Must stay LAST, after all API routes.
if FRONTEND_DIR.is_dir():
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")