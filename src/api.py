from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import ingest
from query import answer_with_sources, collection

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Free hosts often wipe the disk, so rebuild the index if it is empty.
    if collection.count() == 0:
        ingest.main()
    yield


app = FastAPI(lifespan=lifespan)


class Question(BaseModel):
    question: str = Field(min_length=3, max_length=500)   # caps API spend


@app.get("/health")
def health():
    return {"ok": True, "chunks": collection.count()}


@app.post("/ask")
def ask(body: Question):
    text, sources = answer_with_sources(body.question)
    return {"answer": text, "sources": sources}


# Must come AFTER the API routes, or it will swallow them.
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")