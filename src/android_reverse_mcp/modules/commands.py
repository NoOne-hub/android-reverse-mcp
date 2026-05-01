from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _bundled_command(name: str) -> str | None:
    env_name = f"{name.upper().replace('-', '_')}_BIN"
    env_path = os.environ.get(env_name)
    if env_path and Path(env_path).exists():
        return env_path
    candidate = PROJECT_ROOT / "bin" / name
    if candidate.exists():
        return str(candidate)
    return None


def ensure_command(name: str) -> str:
    bundled = _bundled_command(name)
    if bundled:
        return bundled
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
