from __future__ import annotations

from types import SimpleNamespace

import pytest

from android_reverse_mcp.native_backends import client


class DummyItem:
    def __init__(self, text: str | None) -> None:
        self.text = text


class DummyResult:
    def __init__(
        self,
        *,
        is_error: bool = False,
        structured_content: dict | None = None,
        content: list[DummyItem] | None = None,
        dumped: dict | None = None,
    ) -> None:
        self.isError = is_error
        self.structuredContent = structured_content
        self.content = content or []
        self._dumped = dumped or {}

    def model_dump(self, *, mode: str, exclude_none: bool) -> dict:
        assert mode == "json"
        assert exclude_none is True
        return self._dumped


class DummySession:
    def __init__(self, responses: list[object]) -> None:
        self._responses = iter(responses)
        self.requests: list[tuple[object, object, object]] = []
        self.list_calls: list[object] = []

    async def send_request(self, request, result_type, request_read_timeout_seconds=None):
        self.requests.append((request, result_type, request_read_timeout_seconds))
        return next(self._responses)

    async def list_tools(self, cursor=None):
        self.list_calls.append(cursor)
        return next(self._responses)


class DummyTool:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def model_dump(self, *, mode: str, exclude_none: bool) -> dict:
        assert mode == "json"
        assert exclude_none is True
        return self.payload


class DummyListResult:
    def __init__(self, tools: list[dict], next_cursor: str | None = None) -> None:
        self.tools = [DummyTool(tool) for tool in tools]
        self.nextCursor = next_cursor


@pytest.mark.parametrize(
    ("endpoint", "expected"),
    [
        ("tcp://backend-host:8765", "tcp://backend-host:8765"),
        ("http://backend-host:8765/mcp", "http://backend-host:8765/mcp"),
        ("https://backend-host:8765/mcp", "https://backend-host:8765/mcp"),
        ("backend-host:8765", "http://backend-host:8765/mcp"),
    ],
)
def test_normalize_endpoint_accepts_supported_formats(endpoint, expected):
    assert client.normalize_endpoint(endpoint) == expected


@pytest.mark.parametrize(
    ("endpoint", "message"),
    [
        ("backend-host", "非法 native backend 地址"),
        (":8765", "非法 native backend 地址"),
        ("backend-host:notaport", "非法 native backend 端口"),
    ],
)
def test_normalize_endpoint_rejects_invalid_endpoint_strings(endpoint, message):
    with pytest.raises(client.NativeBackendClientError, match=message):
        client.normalize_endpoint(endpoint)


def test_normalize_tool_result_returns_payload_and_content():
    result = client.normalize_tool_result(
        "program.open",
        DummyResult(
            structured_content={"session_id": "s1"},
            content=[DummyItem("opened")],
            dumped={"structuredContent": {"session_id": "s1"}, "content": [{"text": "opened"}]},
        ),
    )

    assert result == {
        "ok": True,
        "tool": "program.open",
        "payload": {"session_id": "s1"},
        "content": ["opened"],
        "raw_result": {"structuredContent": {"session_id": "s1"}, "content": [{"text": "opened"}]},
    }


def test_normalize_tool_result_returns_tool_error_result():
    result = client.normalize_tool_result(
        "program.open",
        DummyResult(
            is_error=True,
            content=[DummyItem("error: path does not exist")],
            dumped={"isError": True, "content": [{"text": "error: path does not exist"}]},
        ),
    )

    assert result == {
        "ok": False,
        "tool": "program.open",
        "error": "error: path does not exist",
        "raw_result": {"isError": True, "content": [{"text": "error: path does not exist"}]},
    }


@pytest.mark.anyio
async def test_call_tool_dispatches_tcp_endpoints_to_ghidra_bridge(monkeypatch):
    async def fake_call_tool(endpoint, tool_name, arguments, timeout=300):
        return {"ok": True, "endpoint": endpoint, "tool": tool_name, "arguments": arguments, "timeout": timeout}

    monkeypatch.setattr(client.ghidra_bridge, "call_tool", fake_call_tool)

    result = await client.call_tool("tcp://ghidra-sidecar:8765", "program.open", {"path": "/tmp/lib.so"}, timeout=33)

    assert result == {
        "ok": True,
        "endpoint": "tcp://ghidra-sidecar:8765",
        "tool": "program.open",
        "arguments": {"path": "/tmp/lib.so"},
        "timeout": 33,
    }


@pytest.mark.anyio
async def test_list_tools_dispatches_tcp_endpoints_to_ghidra_bridge(monkeypatch):
    async def fake_list_tools(endpoint, page_size=64):
        return {"ok": True, "endpoint": endpoint, "page_size": page_size}

    monkeypatch.setattr(client.ghidra_bridge, "list_tools", fake_list_tools)

    result = await client.list_tools("tcp://ghidra-sidecar:8765", page_size=7)

    assert result == {"ok": True, "endpoint": "tcp://ghidra-sidecar:8765", "page_size": 7}


@pytest.mark.anyio
async def test_call_tool_uses_http_session_and_closes_it(monkeypatch):
    session = DummySession(
        [
            DummyResult(
                structured_content={"session_id": "s1"},
                content=[DummyItem("opened")],
                dumped={"structuredContent": {"session_id": "s1"}, "content": [{"text": "opened"}]},
            )
        ]
    )
    closed: list[tuple[object, object]] = []

    async def fake_open_session(endpoint, timeout):
        assert endpoint == "http://backend-host:8765/mcp"
        assert timeout == 45
        return session, "transport"

    async def fake_close_session(opened_session, transport_cm):
        closed.append((opened_session, transport_cm))

    monkeypatch.setattr(client, "_open_session", fake_open_session)
    monkeypatch.setattr(client, "_close_session", fake_close_session)

    result = await client.call_tool("backend-host:8765", "program.open", {"path": "/tmp/lib.so"}, timeout=45)

    assert result["ok"] is True
    assert result["payload"] == {"session_id": "s1"}
    assert closed == [(session, "transport")]
    assert len(session.requests) == 1


@pytest.mark.anyio
async def test_call_tool_wraps_http_session_errors_and_closes(monkeypatch):
    session = DummySession([])
    closed: list[tuple[object, object]] = []

    async def fake_open_session(endpoint, timeout):
        return session, "transport"

    async def fake_close_session(opened_session, transport_cm):
        closed.append((opened_session, transport_cm))

    async def fail_send_request(request, result_type, request_read_timeout_seconds=None):
        raise RuntimeError("boom")

    session.send_request = fail_send_request
    monkeypatch.setattr(client, "_open_session", fake_open_session)
    monkeypatch.setattr(client, "_close_session", fake_close_session)

    result = await client.call_tool("http://backend-host:8765/mcp", "program.open")

    assert result == {"ok": False, "tool": "program.open", "error": "RuntimeError: boom"}
    assert closed == [(session, "transport")]


@pytest.mark.anyio
async def test_list_tools_reads_paginated_http_responses(monkeypatch):
    session = DummySession(
        [
            DummyListResult([{"name": "program.open"}], next_cursor="next-1"),
            DummyListResult([{"name": "function.list"}], next_cursor=None),
        ]
    )
    closed: list[tuple[object, object]] = []

    async def fake_open_session(endpoint, timeout):
        assert endpoint == "http://backend-host:8765/mcp"
        assert timeout == 22
        return session, "transport"

    async def fake_close_session(opened_session, transport_cm):
        closed.append((opened_session, transport_cm))

    monkeypatch.setattr(client, "_open_session", fake_open_session)
    monkeypatch.setattr(client, "_close_session", fake_close_session)

    result = await client.list_tools("backend-host:8765", page_size=1, timeout=22)

    assert result == {
        "ok": True,
        "tools": [{"name": "program.open"}, {"name": "function.list"}],
        "total": 2,
    }
    assert session.list_calls == [None, "next-1"]
    assert closed == [(session, "transport")]


@pytest.mark.anyio
async def test_list_tools_wraps_http_errors(monkeypatch):
    async def fake_open_session(endpoint, timeout):
        raise RuntimeError("connect failed")

    monkeypatch.setattr(client, "_open_session", fake_open_session)

    result = await client.list_tools("backend-host:8765")

    assert result == {"ok": False, "error": "RuntimeError: connect failed"}
