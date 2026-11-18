from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import admin
import otp
import documents
from query import answer_with_sources, collection

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"


@asynccontextmanager
async def lifespan(app: FastAPI):
    otp.verify_link()                      # refuse to start if the chat id doesn't match the handle
    count = documents.rebuild_index()      # Firestore → Chroma
    print(f"Index rebuilt from Firestore: {count} chunks")
    yield


app = FastAPI(lifespan=lifespan)
app.include_router(admin.public)
app.include_router(admin.router)


class Question(BaseModel):
    question: str = Field(min_length=3, max_length=500)


@app.get("/health")
def health():
    return {"ok": True, "chunks": collection.count()}


@app.post("/ask")
def ask(body: Question):
    text, sources = answer_with_sources(body.question)
    return {"answer": text, "sources": sources}


# Must stay LAST, after all API routes.
if FRONTEND_DIR.is_dir():
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")