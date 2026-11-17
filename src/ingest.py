from pathlib import Path

import chromadb
from pypdf import PdfReader

DATA_DIR = Path("data")
DB_DIR = "chroma_db"
CHUNK_WORDS = 4000      # words per chunk
OVERLAP_WORDS = 50     # shared words between neighbouring chunks


def read_file(path: Path) -> str:
    """Return the text of a .pdf or .txt file."""
    if path.suffix.lower() == ".pdf":
        reader = PdfReader(str(path))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    return path.read_text(encoding="utf-8", errors="ignore")


def chunk_text(text: str) -> list[str]:
    """Split text into overlapping chunks of roughly CHUNK_WORDS words."""
    words = text.split()
    chunks = []
    step = CHUNK_WORDS - OVERLAP_WORDS
    for start in range(0, len(words), step):
        piece = words[start:start + CHUNK_WORDS]
        if piece:
            chunks.append(" ".join(piece))
    return chunks


def main():
    client = chromadb.PersistentClient(path=DB_DIR)
    collection = client.get_or_create_collection("docs")

    files = [p for p in DATA_DIR.iterdir() if p.suffix.lower() in {".pdf", ".txt"}]
    if not files:
        print("No .pdf or .txt files found in data/")
        return

    for path in files:
        chunks = chunk_text(read_file(path))
        if not chunks:
            print(f"Skipping {path.name}: no text extracted")
            continue
        collection.upsert(
            documents=chunks,
            ids=[f"{path.name}-{i}" for i in range(len(chunks))],
            metadatas=[{"source": path.name, "chunk": i} for i in range(len(chunks))],
        )
        print(f"Ingested {path.name}: {len(chunks)} chunks")


if __name__ == "__main__":
    main()