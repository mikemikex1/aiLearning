"""FastAPI batch layer for AI Learning Phase 1 (Project runtime removed)."""
from __future__ import annotations

import uuid

from fastapi import BackgroundTasks, FastAPI, HTTPException, Response
from pydantic import BaseModel, Field

from config.settings import EMBEDDING_MODEL, MODEL_FLASH, MODEL_LITE
from src.agents.browser_rag import run_daily_ingest
from src.agents.news_curator import list_all_top3, load_top3, pick_top3
from src.agents.news_feed import export_atom
from src.agents.search_agent import answer
from src.schemas.error_log import read_errors

app = FastAPI(
    title="AI Learning Batch API",
    version="0.1.0",
    description="Headless HTTP layer over ingest/search/news flows.",
)

# In-memory store for background ingest jobs (keyed by job_id).
# Entries: {status: "running"|"done"|"failed", result?: dict, error?: str}
_ingest_jobs: dict[str, dict] = {}


def _run_ingest_job(job_id: str) -> None:
    try:
        result = run_daily_ingest()
        _ingest_jobs[job_id] = {"status": "done", "result": result}
    except Exception as e:  # noqa: BLE001
        _ingest_jobs[job_id] = {"status": "failed", "error": str(e)}


class SearchReq(BaseModel):
    query: str = Field(..., min_length=1)
    k: int = 4


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "models": {"simple": MODEL_LITE, "complex": MODEL_FLASH, "embedding": EMBEDDING_MODEL},
        "version": app.version,
        "project_runtime": "disabled",
    }


@app.post("/ingest")
def ingest(background_tasks: BackgroundTasks) -> dict:
    job_id = uuid.uuid4().hex
    _ingest_jobs[job_id] = {"status": "running"}
    background_tasks.add_task(_run_ingest_job, job_id)
    return {"job_id": job_id, "status": "running"}


@app.get("/ingest/status/{job_id}")
def ingest_status(job_id: str) -> dict:
    job = _ingest_jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"job {job_id!r} not found")
    return {"job_id": job_id, **job}


@app.post("/search")
def search(req: SearchReq) -> dict:
    try:
        return answer(req.query, k=req.k)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"search failed: {e}")


@app.get("/news/top3")
def news_top3(date: str, force: bool = False) -> dict:
    try:
        cached = load_top3(date) if not force else None
        return cached or pick_top3(date, force=force)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"news_top3 failed: {e}")


@app.get("/news/atom")
def news_atom(limit: int = 30):
    try:
        xml = export_atom(limit=limit)
        return Response(content=xml, media_type="application/atom+xml")
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"news_atom failed: {e}")


@app.get("/news/archive")
def news_archive() -> dict:
    return {"payloads": list_all_top3()}


@app.get("/errors")
def errors(limit: int = 50) -> dict:
    return {"entries": read_errors(limit=limit)}
