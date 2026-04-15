"""Index generated projects (blueprint, code, stability report) into the
same Parent-Document RAG store so the Search Agent can cite them."""
from __future__ import annotations
import json
from pathlib import Path
from src.rag.parent_retriever import ingest


def index_project(project_dir: str | Path) -> int:
    pdir = Path(project_dir)
    if not pdir.exists():
        return 0
    docs = []
    bp_file = pdir / "blueprint.json"
    code_file = pdir / "main.py"
    report_file = pdir / "stability_report.md"
    bp: dict = {}
    if bp_file.exists():
        try:
            bp = json.loads(bp_file.read_text())
        except Exception:  # noqa: BLE001
            bp = {}

    base_meta = {
        "source": "project",
        "project_id": bp.get("project_id", pdir.name),
        "title": bp.get("title", pdir.name),
        "topic": bp.get("topic", ""),
        "link": f"file://{pdir.resolve()}",
    }

    if bp:
        docs.append({
            "text": f"Blueprint for '{base_meta['title']}':\n" + json.dumps(bp, indent=2),
            "metadata": {**base_meta, "kind": "blueprint",
                         "file": str(bp_file.name)},
        })
    if code_file.exists():
        docs.append({
            "text": code_file.read_text(),
            "metadata": {**base_meta, "kind": "code", "file": "main.py"},
        })
    if report_file.exists():
        docs.append({
            "text": report_file.read_text(),
            "metadata": {**base_meta, "kind": "stability_report",
                         "file": "stability_report.md"},
        })
    return ingest(docs) if docs else 0
