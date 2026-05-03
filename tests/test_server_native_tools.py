from __future__ import annotations

from pathlib import Path

import pytest

from android_reverse_mcp import server

README_PATH = Path(__file__).resolve().parents[1] / "README.md"


@pytest.mark.anyio
async def test_health_reports_only_native_backend(monkeypatch):
    monkeypatch.setattr(server, "_native_backend", FakeBackend(), raising=False)

    result = await server.health()

    assert result["native_backend"] == "ida"
    assert result["native_enabled"] is True
    assert "ghidra_backend" not in result
    assert "ghidra_enabled" not in result


class FakeBackend:
    def backend_name(self):
        return "ida"

    async def health(self):
        return {"ok": True, "backend": "ida"}

    async def list_functions(self, **kwargs):
        return {"ok": True, "backend": "ida", "received": kwargs}

    async def open_program(self, **kwargs):
        return {
            "ok": True,
            "session_id": "sess-1",
            "project_location": kwargs["project_location"],
            "received": kwargs,
        }


class FakeWorkspace:
    def __init__(self) -> None:
        self.materialize_call: dict | None = None
        self.project_root_relative_path: str | None = None

    def materialize_native_library(self, relative_path: str, *, from_baseline: bool = False) -> Path:
        self.materialize_call = {
            "relative_path": relative_path,
            "from_baseline": from_baseline,
        }
        return Path("/tmp/materialized/libfoo.so")

    def get_native_analysis_dir(self, relative_path: str) -> Path:
        self.project_root_relative_path = relative_path
        return Path("/tmp/native-project")


@pytest.mark.anyio
async def test_native_health_uses_selected_backend(monkeypatch):
    monkeypatch.setattr(server, "_native_backend", FakeBackend(), raising=False)

    result = await server.native_health()

    assert result == {"ok": True, "backend": "ida"}


@pytest.mark.anyio
async def test_native_list_functions_uses_selected_backend(monkeypatch):
    monkeypatch.setattr(server, "_native_backend", FakeBackend(), raising=False)

    result = await server.native_list_functions("sess-1", query="sub_", offset=5, limit=10)

    assert result == {
        "ok": True,
        "backend": "ida",
        "received": {
            "session_id": "sess-1",
            "query": "sub_",
            "offset": 5,
            "limit": 10,
        },
    }


def test_server_no_longer_exposes_ghidra_tool_wrappers():
    assert not hasattr(server, "ghidra_health")
    assert not hasattr(server, "ghidra_list_remote_tools")
    assert not hasattr(server, "ghidra_list_sessions")
    assert not hasattr(server, "ghidra_list_functions")


def test_readme_prefers_native_tools_over_ghidra_tools():
    readme = README_PATH.read_text(encoding="utf-8")

    assert "native_list_functions" in readme
    assert "native_decompile_function" in readme
    assert "native_xrefs_to" in readme
    assert "ghidra_list_functions" not in readme
    assert "ghidra_decompile_function" not in readme
    assert "ghidra_xrefs_to" not in readme


@pytest.mark.anyio
async def test_open_native_library_uses_selected_backend_after_materializing_workspace(monkeypatch):
    fake_workspace = FakeWorkspace()
    fake_backend = FakeBackend()
    monkeypatch.setattr(server, "_native_backend", fake_backend, raising=False)
    monkeypatch.setattr(server, "_workspace_manager", fake_workspace, raising=False)

    result = await server.open_native_library("lib/arm64-v8a/libfoo.so", run_auto_analysis=False, from_baseline=True)

    assert fake_workspace.materialize_call == {
        "relative_path": "lib/arm64-v8a/libfoo.so",
        "from_baseline": True,
    }
    assert fake_workspace.project_root_relative_path == "lib/arm64-v8a/libfoo.so"
    assert result["ok"] is True
    assert result["session_id"] == "sess-1"
    assert result["library"] == {
        "relative_path": "lib/arm64-v8a/libfoo.so",
        "materialized_path": "/tmp/materialized/libfoo.so",
        "from_baseline": True,
        "native_project_root": "/tmp/native-project",
    }
    assert result["project_location"] == "/tmp/native-project"
    assert result["received"] == {
        "path": "/tmp/materialized/libfoo.so",
        "read_only": False,
        "update_analysis": False,
        "project_location": "/tmp/native-project",
        "project_name": "native",
        "program_name": "libfoo.so",
    }


@pytest.mark.anyio
async def test_native_health_returns_error_when_backend_unset(monkeypatch):
    monkeypatch.setattr(server, "_native_backend", None, raising=False)

    result = await server.native_health()

    assert result == {"ok": False, "error": "RuntimeError: native backend 未配置"}


@pytest.mark.anyio
async def test_open_native_library_returns_error_when_workspace_materialization_fails(monkeypatch):
    class FailingWorkspace(FakeWorkspace):
        def materialize_native_library(self, relative_path: str, *, from_baseline: bool = False) -> Path:
            raise FileNotFoundError(relative_path)

    monkeypatch.setattr(server, "_native_backend", FakeBackend(), raising=False)
    monkeypatch.setattr(server, "_workspace_manager", FailingWorkspace(), raising=False)

    result = await server.open_native_library("lib/missing.so")

    assert result == {"ok": False, "error": "FileNotFoundError: lib/missing.so"}


@pytest.mark.anyio
async def test_open_native_library_returns_error_when_backend_open_fails(monkeypatch):
    class FailingBackend(FakeBackend):
        async def open_program(self, **kwargs):
            raise RuntimeError("boom")

    monkeypatch.setattr(server, "_native_backend", FailingBackend(), raising=False)
    monkeypatch.setattr(server, "_workspace_manager", FakeWorkspace(), raising=False)

    result = await server.open_native_library("lib/arm64-v8a/libfoo.so")

    assert result == {"ok": False, "error": "RuntimeError: boom"}
