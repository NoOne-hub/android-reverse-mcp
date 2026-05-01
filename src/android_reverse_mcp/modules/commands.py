from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


def ensure_command(name: str) -> str:
    path = shutil.which(name)
    if not path:
        raise RuntimeError(f"命令不存在: {name}")
    return path


def run_command(cmd: list[str], *, cwd: str | Path | None = None) -> dict:
    proc = subprocess.run(  # noqa: S603
        cmd,
        cwd=str(cwd) if cwd else None,
        text=True,
        capture_output=True,
        check=False,
    )
    return {
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "command": cmd,
        "cwd": None if cwd is None else str(cwd),
    }
