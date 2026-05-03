from __future__ import annotations

from datetime import timedelta
from typing import Any

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
import mcp.types as types

from ..modules import ghidra_bridge


class NativeBackendClientError(RuntimeError):
    pass


def normalize_endpoint(endpoint: str) -> str:
    value = endpoint.strip()
    if value.startswith(("http://", "https://", "tcp://")):
        return value
    if ":" not in value:
        raise NativeBackendClientError(f"非法 native backend 地址: {endpoint}")
    host, port_text = value.rsplit(":", 1)
    if not host:
        raise NativeBackendClientError(f"非法 native backend 地址: {endpoint}")
    try:
        port = int(port_text)
    except ValueError as exc:
        raise NativeBackendClientError(f"非法 native backend 端口: {endpoint}") from exc
    return f"http://{host}:{port}/mcp"


async def _open_session(endpoint: str, timeout: int) -> tuple[ClientSession, Any]:
    url = normalize_endpoint(endpoint)
    transport_cm = streamablehttp_client(url, timeout=timeout, sse_read_timeout=timeout)
    read_stream, write_stream, _ = await transport_cm.__aenter__()
    session = ClientSession(read_stream, write_stream, read_timeout_seconds=timedelta(seconds=timeout))
    await session.__aenter__()
    try:
        await session.initialize()
    except Exception:
        await session.__aexit__(None, None, None)
        await transport_cm.__aexit__(None, None, None)
        raise
    return session, transport_cm


async def _close_session(session: ClientSession | None, transport_cm: Any) -> None:
    if session is not None:
        await session.__aexit__(None, None, None)
    if transport_cm is not None:
        await transport_cm.__aexit__(None, None, None)


def normalize_tool_result(tool_name: str, result: Any) -> dict[str, Any]:
    if getattr(result, "isError", False):
        text_parts = []
        for item in getattr(result, "content", []) or []:
            text = getattr(item, "text", None)
            if text is not None:
                text_parts.append(text)
        return {
            "ok": False,
            "tool": tool_name,
            "error": "\n".join(text_parts) or "unknown error",
            "raw_result": result.model_dump(mode="json", exclude_none=True),
        }

    structured = getattr(result, "structuredContent", None)
    content_items = getattr(result, "content", []) or []
    texts = [
        item.text
        for item in content_items
        if getattr(item, "text", None) is not None
    ]
    return {
        "ok": True,
        "tool": tool_name,
        "payload": structured,
        "content": texts,
        "raw_result": result.model_dump(mode="json", exclude_none=True),
    }


async def call_tool(
    endpoint: str,
    tool_name: str,
    arguments: dict[str, Any] | None = None,
    *,
    timeout: int = 300,
) -> dict[str, Any]:
    normalized = normalize_endpoint(endpoint)
    if normalized.startswith("tcp://"):
        return await ghidra_bridge.call_tool(normalized, tool_name, arguments, timeout=timeout)

    session: ClientSession | None = None
    transport_cm: Any = None
    try:
        session, transport_cm = await _open_session(normalized, timeout)
        result = await session.send_request(
            types.ClientRequest(
                types.CallToolRequest(
                    params=types.CallToolRequestParams(name=tool_name, arguments=arguments or {}),
                )
            ),
            types.CallToolResult,
            request_read_timeout_seconds=timedelta(seconds=timeout),
        )
        return normalize_tool_result(tool_name, result)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "tool": tool_name, "error": f"{type(exc).__name__}: {exc}"}
    finally:
        await _close_session(session, transport_cm)


async def list_tools(
    endpoint: str,
    *,
    page_size: int = 64,
    timeout: int = 300,
) -> dict[str, Any]:
    normalized = normalize_endpoint(endpoint)
    if normalized.startswith("tcp://"):
        return await ghidra_bridge.list_tools(normalized, page_size=page_size)

    session: ClientSession | None = None
    transport_cm: Any = None
    try:
        session, transport_cm = await _open_session(normalized, timeout)
        cursor = None
        tools: list[dict[str, Any]] = []
        while True:
            result = await session.list_tools(cursor=cursor)
            tools.extend(tool.model_dump(mode="json", exclude_none=True) for tool in result.tools)
            cursor = result.nextCursor
            if not cursor:
                break
        return {"ok": True, "tools": tools, "total": len(tools)}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    finally:
        await _close_session(session, transport_cm)
