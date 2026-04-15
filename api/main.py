"""FastAPI batch layer for AI Learning Phase 1.

Run with:
    uvicorn api.main:app --reload --port 8000

Endpoints
---------
GET  /health              — liveness + model routing snapshot
POST /ingest              — trigger the daily Browser/RAG ingest
POST /search    {query}   — RAG-backed Q&A with citations
POST /plan      {topic}   — run Planner only, return blueprint.json
POST /build     {topic,   — run full Planner→Programmer→Tester pipeline
                 blueprint?: dict}
GET  /errors?limit=50     — tail of structured error_log.json
"""
from __future__ import annotations
from typing import Any
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from config.settings import MODEL_LITE, MODEL_FLASH
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
        "models": {"simple": MODEL_LITE, "complex": MODEL_FLASH},
        "version": app.version,
    }


@app.post("/ingest")
def ingest() -> dict:
    try:
        return run_daily_ingest()
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"ingest failed: {e}")


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
