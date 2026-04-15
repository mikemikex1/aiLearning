"""Zip a generated project directory to an in-memory archive."""
from __future__ import annotations
import io
import zipfile
from pathlib import Path


def zip_project(project_dir: str | Path) -> bytes:
    pdir = Path(project_dir)
    if not pdir.exists() or not pdir.is_dir():
        raise FileNotFoundError(f"{pdir} does not exist")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in pdir.rglob("*"):
            if p.is_file():
                zf.write(p, arcname=p.relative_to(pdir.parent))
    return buf.getvalue()
