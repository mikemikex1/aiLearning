"""Parent-Document Retrieval on ChromaDB.

Language-routed embedding strategy:
- English docs/query -> BAAI/bge-base-en-v1.5
- Chinese docs/query -> shibing624/text2vec-base-chinese

If sentence-transformers models are unavailable, fallback to Chroma default
local embedding function for resilience.
"""
from __future__ import annotations

from datetime import datetime
import re
import uuid
from typing import Iterable

import chromadb
from chromadb.utils import embedding_functions

from config.settings import CHROMA_DIR

try:
    from sentence_transformers import SentenceTransformer
except Exception:  # pragma: no cover - optional dependency at runtime
    SentenceTransformer = None  # type: ignore[assignment]

_client = chromadb.PersistentClient(path=str(CHROMA_DIR))
_fallback_embed = embedding_functions.DefaultEmbeddingFunction()

EMBED_ZH_MODEL = "shibing624/text2vec-base-chinese"
EMBED_EN_MODEL = "BAAI/bge-base-en-v1.5"

_model_cache: dict[str, object] = {}
_model_failed: set[str] = set()


def _split_parent(text: str, size: int = 1500) -> list[str]:
    return [text[i:i + size] for i in range(0, len(text), size)] or [text]


def _split_child(parent: str, size: int = 300) -> list[str]:
    return [parent[i:i + size] for i in range(0, len(parent), size)] or [parent]


def _detect_language(text: str) -> str:
    """Heuristic language detection: returns 'zh' or 'en'."""
    if not text:
        return "en"
    zh_chars = len(re.findall(r"[\u4e00-\u9fff]", text))
    latin_chars = len(re.findall(r"[A-Za-z]", text))
    if zh_chars >= 12:
        return "zh"
    if zh_chars > 0 and zh_chars >= max(3, latin_chars // 3):
        return "zh"
    return "en"


def _backend_for_lang(lang: str) -> str:
    return "st_zh" if lang == "zh" else "st_en"


def _collection_name_for_backend(backend: str) -> str:
    return f"children_{backend}"


def _load_st_model(model_name: str):
    if model_name in _model_failed:
        return None
    if model_name in _model_cache:
        return _model_cache[model_name]
    if SentenceTransformer is None:
        _model_failed.add(model_name)
        return None
    try:
        model = SentenceTransformer(model_name)
        _model_cache[model_name] = model
        return model
    except Exception:
        _model_failed.add(model_name)
        return None


def _embed_with_backend(texts: list[str], backend: str) -> list[list[float]]:
    if backend == "st_zh":
        model = _load_st_model(EMBED_ZH_MODEL)
    elif backend == "st_en":
        model = _load_st_model(EMBED_EN_MODEL)
    elif backend == "default":
        model = None
    else:
        model = None

    if model is not None:
        arr = model.encode(texts, normalize_embeddings=True, convert_to_numpy=True)  # type: ignore[union-attr]
        return arr.tolist()
    return _fallback_embed(texts)


def _embed_query_with_backend(query: str, backend: str) -> list[float]:
    return _embed_with_backend([query], backend)[0]


def _retrieve_lexical(query: str, k: int, parents) -> list[dict]:
    all_docs = parents.get()
    docs = all_docs.get("documents", []) or []
    metas = all_docs.get("metadatas", []) or []
    if not docs:
        return []
    q_lang = _detect_language(query)
    tokens = re.findall(r"[a-zA-Z0-9\u4e00-\u9fff]{2,}", query.lower())
    scored: list[tuple[int, int]] = []
    for i, (txt, meta) in enumerate(zip(docs, metas)):
        if (meta or {}).get("source") == "test":
            continue
        blob = f"{(meta or {}).get('title', '')} {txt}".lower()
        score = sum(1 for t in tokens if t in blob)
        if (meta or {}).get("language") == q_lang:
            score += 2
        scored.append((score, i))
    scored.sort(key=lambda x: x[0], reverse=True)
    picked = [idx for score, idx in scored[:k] if score > 0]
    if not picked:
        picked = list(range(min(k, len(docs))))
    return [{"text": docs[i], "metadata": metas[i]} for i in picked]


def ingest(docs: Iterable[dict]) -> int:
    """docs: iterable of {'id', 'text', 'metadata'} stores parent+child chunks."""
    parents = _client.get_or_create_collection("parents")
    total = 0
    for doc in docs:
        text = doc.get("text", "") or ""
        base_meta = dict(doc.get("metadata", {}) or {})
        lang = _detect_language(f"{base_meta.get('title', '')}\n{text}")
        backend = _backend_for_lang(lang)

        for p_text in _split_parent(text):
            pid = str(uuid.uuid4())
            p_meta = {"language": lang, "embedding_backend": backend, **base_meta}
            parents.add(ids=[pid], documents=[p_text], metadatas=[p_meta])

            c_texts = _split_child(p_text)
            c_vecs = _embed_with_backend(c_texts, backend)
            children = _client.get_or_create_collection(
                _collection_name_for_backend(backend),
                embedding_function=None,
            )
            children.add(
                ids=[f"{pid}:{i}" for i in range(len(c_texts))],
                documents=c_texts,
                embeddings=c_vecs,
                metadatas=[{"parent_id": pid, "language": lang, "embedding_backend": backend, **base_meta} for _ in c_texts],
            )
            total += 1
    return total


def retrieve(query: str, k: int = 4) -> list[dict]:
    """Query language-routed child index; fallback to lexical search."""
    parents = _client.get_or_create_collection("parents")
    q_lang = _detect_language(query)

    preferred = _backend_for_lang(q_lang)
    secondary = "st_en" if preferred == "st_zh" else "st_zh"
    backends = [preferred, secondary, "default"]

    parent_ids: list[str] = []
    for backend in backends:
        children = _client.get_or_create_collection(_collection_name_for_backend(backend))
        qvec = _embed_query_with_backend(query, backend)
        try:
            res = children.query(query_embeddings=[qvec], n_results=k * 3)
        except Exception:
            continue
        for meta in (res.get("metadatas", [[]])[0] or []):
            pid = meta.get("parent_id")
            if pid and pid not in parent_ids:
                parent_ids.append(pid)
            if len(parent_ids) >= k:
                break
        if len(parent_ids) >= k:
            break

    if not parent_ids:
        return _retrieve_lexical(query, k, parents)

    pres = parents.get(ids=parent_ids)
    rows = [{"text": t, "metadata": m} for t, m in zip(pres.get("documents", []), pres.get("metadatas", []))]
    real_rows = [r for r in rows if (r.get("metadata", {}) or {}).get("source") != "test"]
    rows = real_rows if real_rows else rows
    rows.sort(key=lambda r: 1 if (r.get("metadata", {}) or {}).get("language") == q_lang else 0, reverse=True)
    return rows[:k]


def list_indexed_items(limit: int = 60) -> list[dict]:
    """Return de-duplicated indexed article metadata from parents collection.

    Only returns real web/article sources (excludes test/project records).
    """
    parents = _client.get_or_create_collection("parents")
    data = parents.get()
    metas = data.get("metadatas", []) or []
    docs = data.get("documents", []) or []

    rows: list[dict] = []
    for meta, doc in zip(metas, docs):
        m = meta or {}
        src = m.get("source", "")
        if src in ("test", "project", ""):
            continue
        rows.append(
            {
                "source": src,
                "title": m.get("title", ""),
                "link": m.get("link", ""),
                "published": m.get("published", ""),
                "fetched_at": m.get("fetched_at", ""),
                "language": m.get("language", ""),
                "summary": (doc or "")[:500],
            }
        )

    # Deduplicate by link/title while preserving the most recent fetched_at.
    def _ts(v: str) -> float:
        if not v:
            return 0.0
        try:
            return datetime.fromisoformat(v.replace("Z", "+00:00")).timestamp()
        except Exception:
            return 0.0

    rows.sort(key=lambda r: _ts(r.get("fetched_at", "")), reverse=True)
    seen: set[str] = set()
    deduped: list[dict] = []
    for r in rows:
        key = (r.get("link") or "").strip() or (r.get("title") or "").strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(r)
        if len(deduped) >= limit:
            break
    return deduped
