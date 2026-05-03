import pytest

from android_reverse_mcp.native_backends.ghidra import GhidraBackend
from android_reverse_mcp.native_backends.ida import IdaBackend


@pytest.mark.anyio
async def test_ghidra_backend_list_functions_maps_query(monkeypatch):
    calls = []

    async def fake_call_tool(endpoint, tool_name, arguments, timeout=300):
        calls.append((endpoint, tool_name, arguments, timeout))
        return {"ok": True, "tool": tool_name, "payload": {"items": []}, "raw_result": {}}

    monkeypatch.setattr("android_reverse_mcp.native_backends.ghidra.call_tool", fake_call_tool)

    backend = GhidraBackend(url="tcp://ghidra-sidecar:8765")
    result = await backend.list_functions(session_id="s1", query="JNI", offset=5, limit=10)

    assert result["ok"] is True
    assert calls == [
        (
            "tcp://ghidra-sidecar:8765",
            "function.list",
            {"session_id": "s1", "offset": 5, "limit": 10, "query": "JNI"},
            300,
        )
    ]


def test_ghidra_backend_exposes_name_and_capabilities():
    backend = GhidraBackend(url="tcp://ghidra-sidecar:8765")

    assert backend.backend_name() == "ghidra"
    assert backend.capabilities.shared_tools == frozenset(
        {
            "health",
            "list_remote_tools",
            "list_sessions",
            "open_program",
            "program_summary",
            "save_program",
            "list_functions",
            "decompile_function",
            "function_report",
            "xrefs_to",
            "xrefs_from",
            "rename_function",
            "list_variables",
            "rename_variable",
            "set_comment",
        }
    )
    assert backend.capabilities.extension_prefix == "native_ghidra_"


@pytest.mark.anyio
async def test_ghidra_backend_open_program_maps_arguments(monkeypatch):
    calls = []

    async def fake_call_tool(endpoint, tool_name, arguments, timeout=300):
        calls.append((endpoint, tool_name, arguments, timeout))
        return {
            "ok": True,
            "tool": tool_name,
            "payload": {"session_id": "s1", "project_location": "/tmp/ghidra"},
            "raw_result": {},
        }

    monkeypatch.setattr("android_reverse_mcp.native_backends.ghidra.call_tool", fake_call_tool)

    backend = GhidraBackend(url="tcp://ghidra-sidecar:8765")
    result = await backend.open_program(
        path="/tmp/libfoo.so",
        read_only=False,
        update_analysis=True,
        project_location="/tmp/ghidra",
        project_name="ghidra",
        program_name="libfoo.so",
    )

    assert result["session_id"] == "s1"
    assert result["project_location"] == "/tmp/ghidra"
    assert calls == [
        (
            "tcp://ghidra-sidecar:8765",
            "program.open",
            {
                "path": "/tmp/libfoo.so",
                "read_only": False,
                "update_analysis": True,
                "project_location": "/tmp/ghidra",
                "project_name": "ghidra",
                "program_name": "libfoo.so",
            },
            1800,
        )
    ]


@pytest.mark.anyio
async def test_ghidra_backend_set_comment_maps_optional_fields(monkeypatch):
    calls = []

    async def fake_call_tool(endpoint, tool_name, arguments, timeout=300):
        calls.append((endpoint, tool_name, arguments, timeout))
        return {"ok": True, "tool": tool_name, "payload": {}, "raw_result": {}}

    monkeypatch.setattr("android_reverse_mcp.native_backends.ghidra.call_tool", fake_call_tool)

    backend = GhidraBackend(url="tcp://ghidra-sidecar:8765")
    await backend.set_comment(
        session_id="s1",
        address="0x401000",
        comment="note",
        scope="listing",
        comment_type="pre",
    )

    assert calls == [
        (
            "tcp://ghidra-sidecar:8765",
            "comment.set",
            {
                "session_id": "s1",
                "address": "0x401000",
                "scope": "listing",
                "comment_type": "pre",
                "comment": "note",
            },
            300,
        )
    ]


def test_ida_backend_exposes_name_and_capabilities():
    backend = IdaBackend(url="http://ida-sidecar:8745/mcp")

    assert backend.backend_name() == "ida"
    assert backend.capabilities.shared_tools == frozenset(
        {
            "health",
            "list_remote_tools",
            "list_sessions",
            "open_program",
            "program_summary",
            "save_program",
            "list_functions",
            "decompile_function",
            "function_report",
            "xrefs_to",
            "xrefs_from",
            "rename_function",
            "list_variables",
            "rename_variable",
            "set_comment",
        }
    )
    assert backend.capabilities.extension_prefix == "native_ida_"


@pytest.mark.anyio
async def test_ida_backend_list_functions_uses_explicit_mapping_table(monkeypatch):
    calls = []

    async def fake_call_tool(endpoint, tool_name, arguments, timeout=300):
        calls.append((endpoint, tool_name, arguments, timeout))
        return {"ok": True, "tool": tool_name, "payload": {"items": []}, "raw_result": {}}

    monkeypatch.setattr("android_reverse_mcp.native_backends.ida.call_tool", fake_call_tool)

    backend = IdaBackend(
        url="http://ida-sidecar:8745/mcp",
        tool_mapping={"list_functions": "list_funcs"},
    )
    result = await backend.list_functions(session_id="s1", query="JNI", offset=5, limit=10)

    assert result["ok"] is True
    assert calls == [
        (
            "http://ida-sidecar:8745/mcp",
            "list_funcs",
            {"queries": [{"offset": 5, "count": 10, "filter": "JNI"}]},
            300,
        )
    ]


@pytest.mark.anyio
async def test_ida_backend_open_program_uses_idalib_open_arguments(monkeypatch):
    calls = []

    async def fake_call_tool(endpoint, tool_name, arguments, timeout=300):
        calls.append((endpoint, tool_name, arguments, timeout))
        return {
            "ok": True,
            "tool": tool_name,
            "payload": {"session": {"session_id": "s1"}},
            "raw_result": {},
        }

    monkeypatch.setattr("android_reverse_mcp.native_backends.ida.call_tool", fake_call_tool)

    backend = IdaBackend(
        url="http://ida-sidecar:8745/mcp",
        tool_mapping={"open_program": "idalib_open"},
    )
    result = await backend.open_program(
        path="/tmp/libfoo.so",
        read_only=False,
        update_analysis=True,
        project_location="/tmp/ignored",
        project_name="ignored",
        program_name="ignored",
    )

    assert result["session_id"] == "s1"
    assert calls == [
        (
            "http://ida-sidecar:8745/mcp",
            "idalib_open",
            {
                "input_path": "/tmp/libfoo.so",
                "run_auto_analysis": True,
            },
            1800,
        )
    ]


@pytest.mark.anyio
async def test_ida_backend_rename_variable_uses_batch_rename(monkeypatch):
    calls = []

    async def fake_call_tool(endpoint, tool_name, arguments, timeout=300):
        calls.append((endpoint, tool_name, arguments, timeout))
        return {"ok": True, "tool": tool_name, "payload": {}, "raw_result": {}}

    monkeypatch.setattr("android_reverse_mcp.native_backends.ida.call_tool", fake_call_tool)

    backend = IdaBackend(
        url="http://ida-sidecar:8745/mcp",
        tool_mapping={"rename_variable": "rename"},
    )
    await backend.rename_variable(
        session_id="s1",
        function_start="0x401000",
        old_name="var_10",
        new_name="length",
    )

    assert calls == [
        (
            "http://ida-sidecar:8745/mcp",
            "rename",
            {
                "batch": {
                    "local": [{"func_addr": "0x401000", "old": "var_10", "new": "length"}],
                    "stack": [{"func_addr": "0x401000", "old": "var_10", "new": "length"}],
                }
            },
            300,
        )
    ]


@pytest.mark.anyio
async def test_ida_backend_raises_for_unconfigured_mapping():
    backend = IdaBackend(url="http://ida-sidecar:8745/mcp")

    with pytest.raises(
        RuntimeError,
        match="IDA backend tool mapping not configured for operation: list_functions",
    ):
        await backend.list_functions(session_id="s1")
