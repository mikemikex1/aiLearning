"""Subprocess runner for generated project code.

Runs `python main.py <args>` inside the project directory with a timeout.
Returns stdout, stderr, return code, and elapsed seconds.
"""
from __future__ import annotations
import subprocess
import sys
import time
from pathlib import Path
from dataclasses import dataclass


@dataclass
class RunResult:
    returncode: int
    stdout: str
    stderr: str
    elapsed: float
    timed_out: bool = False


def run_project(project_dir: str | Path, args: list[str] | None = None,
                timeout: int = 30) -> RunResult:
    pdir = Path(project_dir)
    main = pdir / "main.py"
    if not main.exists():
        return RunResult(returncode=-1, stdout="",
                         stderr=f"main.py not found in {pdir}", elapsed=0.0)
    cmd = [sys.executable, str(main)] + (args or [])
    start = time.monotonic()
    try:
        proc = subprocess.run(
            cmd, cwd=str(pdir), capture_output=True, text=True,
            timeout=timeout, check=False,
        )
        return RunResult(
            returncode=proc.returncode, stdout=proc.stdout,
            stderr=proc.stderr, elapsed=time.monotonic() - start,
        )
    except subprocess.TimeoutExpired as e:
        return RunResult(
            returncode=-9,
            stdout=(e.stdout or "") if isinstance(e.stdout, str) else "",
            stderr=f"TIMEOUT after {timeout}s",
            elapsed=time.monotonic() - start,
            timed_out=True,
        )
    except Exception as e:  # noqa: BLE001
        return RunResult(returncode=-1, stdout="",
                         stderr=f"{type(e).__name__}: {e}",
                         elapsed=time.monotonic() - start)
