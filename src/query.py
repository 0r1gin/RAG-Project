import sys

import anthropic
import chromadb
from dotenv import load_dotenv

load_dotenv(override=True)  # reads ANTHROPIC_API_KEY from .env

MODEL = "claude-sonnet-5-5"   # if you get a model error, check docs.claude.com for current names
N_RESULTS = 3

llm = anthropic.Anthropic()
collection = chromadb.PersistentClient(path="chroma_db").get_or_create_collection("docs")


def retrieve(question: str):
    results = collection.query(query_texts=[question], n_results=N_RESULTS)
    return results["documents"][0], results["metadatas"][0]


def answer(question: str) -> str:
    docs, metas = retrieve(question)
    context = "\n\n".join(
        f"[Source: {m['source']}, chunk {m['chunk']}]\n{d}" for d, m in zip(docs, metas)
    )
    prompt = (
        "Answer the question using ONLY the context below. "
        "If the context doesn't contain the answer, say you don't know. "
        "Mention which source you used.\n\n"
        f"<context>\n{context}\n</context>\n\n"
        f"Question: {question}"
    )
    response = llm.messages.create(
        model=MODEL,
        max_tokens=5000,
        messages=[{"role": "user", "content": prompt}],
    )
    return "".join(block.text for block in response.content if block.type == "text")


if __name__ == "__main__":
    q = " ".join(sys.argv[1:]) or input("Question: ")
    print(answer(q))