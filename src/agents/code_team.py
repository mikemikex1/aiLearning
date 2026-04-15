"""Code Team — LangGraph sequential pipeline:
    planner → [INTERRUPT: human approval] → programmer → tester → report

The graph uses `interrupt_before=["programmer"]` so the Streamlit Project
page can render the blueprint and let the user edit it before code gen.
"""
from __future__ import annotations
import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import TypedDict
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from src.models.router import call_with_fallback
from src.schemas.blueprint import Blueprint
from src.utils.error_handler import record
from src.rag.parent_retriever import retrieve
from config.settings import ROOT


class TeamState(TypedDict, total=False):
    topic: str
    rag_context: str
    blueprint: dict
    code: str
    stability_report: str
    project_dir: str


# ---------------- Planner ----------------
PLAN_PROMPT = """You are a Planner. Produce a STRICT JSON object matching this schema:
{{
 "project_id": str, "title": str, "topic": str, "objective": str,
 "tech_stack": [str], "modules": [{{"name": str, "responsibility": str,
   "inputs": [str], "outputs": [str]}}],
 "entrypoint": "main.py",
 "cli_args": [{{"name": str, "type": str, "required": bool}}],
 "edge_cases": [str], "success_criteria": [str]
}}
Topic: {topic}
RAG context:
{ctx}
Return ONLY the JSON, no prose, no markdown fences.
"""


def _extract_json(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        raise ValueError("No JSON found in Planner output")
    return json.loads(m.group(0))


def planner_node(state: TeamState) -> TeamState:
    topic = state["topic"]
    chunks = retrieve(topic, k=4)
    ctx = "\n---\n".join(c["text"] for c in chunks) or "(no RAG hits)"
    try:
        raw = call_with_fallback("complex", PLAN_PROMPT.format(topic=topic, ctx=ctx))
        bp = Blueprint(**_extract_json(raw)).model_dump()
    except Exception as e:  # noqa: BLE001
        record("LLM_JSON_ERROR", "code_team.planner", str(e),
               {"topic": topic})
        bp = Blueprint(
            project_id=str(uuid.uuid4())[:8], title=f"{topic} starter",
            topic=topic, objective=f"Minimal runnable demo for {topic}",
            tech_stack=["python"],
            modules=[{"name": "main", "responsibility": "entrypoint",
                      "inputs": [], "outputs": []}],
        ).model_dump()
    return {"blueprint": bp, "rag_context": ctx}


# ---------------- Programmer ----------------
PROG_PROMPT = """You are a Programmer. Given this blueprint.json, write a single-file
Python program `main.py` that runs from the terminal with argparse. Include robust
error handling (try/except, empty/None guards). Output ONLY code, no fences.

Blueprint:
{bp}
"""


def programmer_node(state: TeamState) -> TeamState:
    bp = state["blueprint"]
    try:
        code = call_with_fallback("complex", PROG_PROMPT.format(bp=json.dumps(bp, indent=2)))
        code = re.sub(r"^```(?:python)?|```$", "", code.strip(), flags=re.MULTILINE)
    except Exception as e:  # noqa: BLE001
        record("RUNTIME_FAIL", "code_team.programmer", str(e))
        code = "# generation failed\nprint('stub')\n"
    # persist — include timestamp so multiple builds of the same topic coexist
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    pdir = ROOT / "data" / "projects" / f"{bp['project_id']}_{ts}"
    pdir.mkdir(parents=True, exist_ok=True)
    (pdir / "blueprint.json").write_text(json.dumps(bp, indent=2, ensure_ascii=False))
    (pdir / "main.py").write_text(code)
    return {"code": code, "project_dir": str(pdir)}


# ---------------- Tester ----------------
TEST_PROMPT = """You are a Tester focused on STABILITY. Given this code and blueprint,
produce a Markdown stability report covering: empty input, oversized input, None,
API failure mock, timeout. For each case: describe the test, expected behaviour,
and whether the code appears to handle it. End with an overall PASS/FAIL.

Blueprint:
{bp}

Code:
```python
{code}
```
"""


def tester_node(state: TeamState) -> TeamState:
    try:
        report = call_with_fallback("complex",
            TEST_PROMPT.format(bp=json.dumps(state["blueprint"], indent=2),
                               code=state["code"][:6000]))
    except Exception as e:  # noqa: BLE001
        record("RUNTIME_FAIL", "code_team.tester", str(e))
        report = "# Stability report unavailable\n"
    Path(state["project_dir"], "stability_report.md").write_text(report)

    # Auto-index the finished project so Search can cite it.
    try:
        from src.rag.project_indexer import index_project
        index_project(state["project_dir"])
    except Exception as e:  # noqa: BLE001
        record("RETRIEVAL_MISS", "code_team.tester.index", str(e))

    return {"stability_report": report}


# ---------------- Graph ----------------
def _base_graph():
    g = StateGraph(TeamState)
    g.add_node("planner", planner_node)
    g.add_node("programmer", programmer_node)
    g.add_node("tester", tester_node)
    g.add_edge(START, "planner")
    g.add_edge("planner", "programmer")
    g.add_edge("programmer", "tester")
    g.add_edge("tester", END)
    return g


def build_graph():
    """Interactive graph for Streamlit UI (stops before programmer for HITL)."""
    return _base_graph().compile(
        checkpointer=MemorySaver(),
        interrupt_before=["programmer"],
    )


def build_graph_headless():
    """Non-interactive graph for FastAPI / cron — no HITL interrupt."""
    return _base_graph().compile(checkpointer=MemorySaver())


def run_pipeline(topic: str, approved_blueprint: dict | None = None) -> dict:
    """End-to-end run used by the FastAPI batch layer.

    If `approved_blueprint` is provided, it is injected after the planner step.
    """
    import uuid as _uuid
    graph = build_graph_headless()
    cfg = {"configurable": {"thread_id": _uuid.uuid4().hex}}
    initial: TeamState = {"topic": topic}
    if approved_blueprint:
        initial["blueprint"] = approved_blueprint
    for _ in graph.stream(initial, config=cfg):
        pass
    return dict(graph.get_state(cfg).values)


def run_planner_only(topic: str) -> dict:
    """Return just the blueprint for the `/plan` endpoint."""
    state = planner_node({"topic": topic})
    return state.get("blueprint", {})
