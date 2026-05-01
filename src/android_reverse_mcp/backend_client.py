from __future__ import annotations

import atexit
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import httpx

_BACKEND_BASE = os.environ.get("JADX_BACKEND_URL", "http://127.0.0.1:8650")
_BACKEND_PROCESS: subprocess.Popen[str] | None = None


def set_backend_base(url: str) -> None:
    global _BACKEND_BASE
    _BACKEND_BASE = url.rstrip("/")


def get_backend_base() -> str:
    return _BACKEND_BASE


def health_ping() -> dict[str, Any]:
    try:
        with httpx.Client(trust_env=False, timeout=10.0) as client:
            resp = client.get(f"{_BACKEND_BASE}/health")
            resp.raise_for_status()
            return resp.json()
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


def request(endpoint: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    params = {k: v for k, v in (params or {}).items() if v is not None}
    with httpx.Client(trust_env=False, timeout=3600.0) as client:
        resp = client.get(f"{_BACKEND_BASE}/{endpoint.lstrip('/')}", params=params)
        resp.raise_for_status()
        return resp.json()


def wait_until_ready(timeout: float = 60.0) -> None:
    deadline = time.time() + timeout
    last_error = "backend not ready"
    while time.time() < deadline:
        result = health_ping()
        if result.get("ok"):
            return
        last_error = result.get("error", last_error)
        time.sleep(1.0)
    raise RuntimeError(last_error)


def start_backend(
    *,
    backend_host: str,
    backend_port: int,
    backend_jar: str,
    jadx_jar: str,
    apk_path: str | None = None,
    threads: int | None = None,
) -> None:
    global _BACKEND_PROCESS
    if _BACKEND_PROCESS is not None:
        return

    backend_jar_path = Path(backend_jar).resolve()
    jadx_jar_path = Path(jadx_jar).resolve()
    if not backend_jar_path.is_file():
        raise RuntimeError(f"backend jar 不存在: {backend_jar_path}")
    if not jadx_jar_path.is_file():
        raise RuntimeError(f"jadx all jar 不存在: {jadx_jar_path}")

    cmd = [
        "java",
        "-cp",
        f"{backend_jar_path}:{jadx_jar_path}",
        "mcp.jadx.HeadlessJadxBackend",
        "--host",
        backend_host,
        "--port",
        str(backend_port),
    ]
    if apk_path:
        cmd.extend(["--apk", str(Path(apk_path).resolve())])
    if threads:
        cmd.extend(["--threads", str(threads)])

    env = os.environ.copy()
    _BACKEND_PROCESS = subprocess.Popen(  # noqa: S603
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=sys.stderr,
        text=True,
        env=env,
    )
    atexit.register(stop_backend)
    wait_until_ready()


def stop_backend() -> None:
    global _BACKEND_PROCESS
    if _BACKEND_PROCESS is None:
        return
    proc = _BACKEND_PROCESS
    _BACKEND_PROCESS = None
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
