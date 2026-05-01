from __future__ import annotations

import json
from typing import Any

from fastmcp import Client


def _normalize_mcp_url(base_url: str) -> str:
    base = base_url.rstrip('/')
    return base if base.endswith('/mcp') else f'{base}/mcp'


def _content_to_text_list(result: Any) -> list[str]:
    texts: list[str] = []
    for item in getattr(result, 'content', []) or []:
        text = getattr(item, 'text', None)
        if text is not None:
            texts.append(text)
        else:
            texts.append(str(item))
    return texts


def _normalize_result(tool_name: str, result: Any) -> dict[str, Any]:
    payload = getattr(result, 'structured_content', None)
    if payload is None:
        texts = _content_to_text_list(result)
        if len(texts) == 1:
            try:
                payload = json.loads(texts[0])
            except Exception:
                payload = {'text': texts[0]}
        else:
            payload = {'content': texts}
    return {
        'ok': not getattr(result, 'is_error', False),
        'tool': tool_name,
        'payload': payload,
        'content': _content_to_text_list(result),
    }


async def call_tool(base_url: str, tool_name: str, arguments: dict[str, Any] | None = None, *, timeout: int = 300) -> dict[str, Any]:
    try:
        async with Client(_normalize_mcp_url(base_url), timeout=timeout) as client:
            result = await client.call_tool(tool_name, arguments or {}, raise_on_error=False, timeout=timeout)
            return _normalize_result(tool_name, result)
    except Exception as exc:  # noqa: BLE001
        return {'ok': False, 'tool': tool_name, 'error': f'{type(exc).__name__}: {exc}'}


async def list_tools(base_url: str, *, max_pages: int = 250) -> dict[str, Any]:
    try:
        async with Client(_normalize_mcp_url(base_url), timeout=60) as client:
            tools = await client.list_tools(max_pages=max_pages)
            return {
                'ok': True,
                'tools': [
                    {
                        'name': tool.name,
                        'description': tool.description,
                        'input_schema': tool.inputSchema,
                    }
                    for tool in tools
                ],
                'total': len(tools),
            }
    except Exception as exc:  # noqa: BLE001
        return {'ok': False, 'error': f'{type(exc).__name__}: {exc}'}
