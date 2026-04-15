"""Parent-Document Retrieval on ChromaDB.

Child chunks (~300 chars) are embedded for recall;
parent chunks (~1500 chars) are returned to preserve code context.
"""
from __future__ import annotations
import uuid
from typing import Iterable
import chromadb
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from config.settings import CHROMA_DIR, EMBEDDING_MODEL, get_api_key

_client = chromadb.PersistentClient(path=str(CHROMA_DIR))


def _embed():
    return GoogleGenerativeAIEmbeddings(
        model=f"models/{EMBEDDING_MODEL}",
        google_api_key=get_api_key(),
    )


def _split_parent(text: str, size: int = 1500) -> list[str]:
    return [text[i:i + size] for i in range(0, len(text), size)] or [text]


def _split_child(parent: str, size: int = 300) -> list[str]:
    return [parent[i:i + size] for i in range(0, len(parent), size)] or [parent]


def ingest(docs: Iterable[dict]) -> int:
    """docs: iterable of {'id', 'text', 'metadata'} — stores parent+child chunks."""
    parents = _client.get_or_create_collection("parents")
    children = _client.get_or_create_collection(
        "children",
        embedding_function=None,  # we supply vectors manually
    )
    emb = _embed()
    total = 0
    for doc in docs:
        for p_text in _split_parent(doc["text"]):
            pid = str(uuid.uuid4())
            parents.add(ids=[pid], documents=[p_text],
                        metadatas=[doc.get("metadata", {})])
            c_texts = _split_child(p_text)
            c_vecs = emb.embed_documents(c_texts)
            children.add(
                ids=[f"{pid}:{i}" for i in range(len(c_texts))],
                documents=c_texts,
                embeddings=c_vecs,
                metadatas=[{"parent_id": pid, **doc.get("metadata", {})}
                           for _ in c_texts],
            )
            total += 1
    return total


def retrieve(query: str, k: int = 4) -> list[dict]:
    """Query child index, return de-duplicated parent chunks."""
    children = _client.get_or_create_collection("children")
    parents = _client.get_or_create_collection("parents")
    emb = _embed()
    qvec = emb.embed_query(query)
    res = children.query(query_embeddings=[qvec], n_results=k * 3)
    parent_ids: list[str] = []
    for meta in (res.get("metadatas", [[]])[0] or []):
        pid = meta.get("parent_id")
        if pid and pid not in parent_ids:
            parent_ids.append(pid)
        if len(parent_ids) >= k:
            break
    if not parent_ids:
        return []
    pres = parents.get(ids=parent_ids)
    return [{"text": t, "metadata": m}
            for t, m in zip(pres.get("documents", []), pres.get("metadatas", []))]
