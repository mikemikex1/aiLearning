"""FastAPI batch layer for AI Learning Phase 1.

Run with:
    uvicorn api.main:app --reload --port 8000

Endpoints
---------
GET  /health                    — liveness + model routing snapshot
POST /ingest                    — start ingest job in background, returns {job_id}
GET  /ingest/status/{job_id}    — poll ingest job status
POST /search    {query}         — RAG-backed Q&A with citations
POST /plan      {topic}         — run Planner only, return blueprint.json
POST /build     {topic,         — run full Planner→Programmer→Tester pipeline
                 blueprint?: dict}
GET  /errors?limit=50           — tail of structured error_log.json
"""
from __future__ import annotations
import uuid
from typing import Any
from fastapi import BackgroundTasks, FastAPI, HTTPException
from pydantic import BaseModel, Field

from config.settings import MODEL_LITE, MODEL_FLASH, EMBEDDING_MODEL
from src.agents.browser_rag import run_daily_ingest
from src.agents.search_agent import answer
from src.agents.code_team import run_planner_only, run_pipeline
from src.agents.news_curator import pick_top3, load_top3, list_all_top3
from src.agents.news_feed import export_atom
from src.schemas.error_log import read_errors
from fastapi import Response

app = FastAPI(
    title="AI Learning — Batch API",
    version="0.1.0",
    description="Headless HTTP layer over the LangGraph pipeline",
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


# ---------------- Schemas ----------------
class SearchReq(BaseModel):
    query: str = Field(..., min_length=1)
    k: int = 4


class PlanReq(BaseModel):
    topic: str = Field(..., min_length=1)


class BuildReq(BaseModel):
    topic: str = Field(..., min_length=1)
    blueprint: dict[str, Any] | None = None  # if omitted, planner runs fresh


# ---------------- Routes ----------------
@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "models": {"simple": MODEL_LITE, "complex": MODEL_FLASH,
                   "embedding": EMBEDDING_MODEL},
        "version": app.version,
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


@app.post("/plan")
def plan(req: PlanReq) -> dict:
    try:
        bp = run_planner_only(req.topic)
        if not bp:
            raise HTTPException(status_code=502, detail="planner returned empty")
        return {"blueprint": bp}
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"plan failed: {e}")


@app.post("/build")
def build(req: BuildReq) -> dict:
    try:
        result = run_pipeline(req.topic, approved_blueprint=req.blueprint)
        return {
            "blueprint": result.get("blueprint"),
            "project_dir": result.get("project_dir"),
            "code_preview": (result.get("code") or "")[:1500],
            "stability_report_preview": (result.get("stability_report") or "")[:1500],
        }
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"build failed: {e}")


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
