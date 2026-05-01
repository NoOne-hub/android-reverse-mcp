from __future__ import annotations

import asyncio
import json
from itertools import count
from typing import Any


_REQUEST_IDS = count(1)


class GhidraBridgeError(RuntimeError):
    pass


def _normalize_endpoint(endpoint: str) -> tuple[str, int]:
    value = endpoint.strip()
    if value.startswith('tcp://'):
        value = value[6:]
    if ':' not in value:
        raise GhidraBridgeError(f'非法 Ghidra backend 地址: {endpoint}')
    host, port_text = value.rsplit(':', 1)
    if not host:
        raise GhidraBridgeError(f'非法 Ghidra backend 地址: {endpoint}')
    try:
        port = int(port_text)
    except ValueError as exc:
        raise GhidraBridgeError(f'非法 Ghidra backend 端口: {endpoint}') from exc
    return host, port


async def _read_json_line(reader: asyncio.StreamReader) -> dict[str, Any]:
    raw = await reader.readline()
    if not raw:
        raise GhidraBridgeError('Ghidra backend 已断开连接')
    try:
        payload = json.loads(raw.decode('utf-8'))
    except Exception as exc:  # noqa: BLE001
        raise GhidraBridgeError(f'Ghidra backend 返回了非法 JSON: {raw[:200]!r}') from exc
    if not isinstance(payload, dict):
        raise GhidraBridgeError(f'Ghidra backend 返回了非法响应: {payload!r}')
    return payload


async def _send_request(writer: asyncio.StreamWriter, payload: dict[str, Any]) -> None:
    writer.write(json.dumps(payload, ensure_ascii=False).encode('utf-8') + b'\n')
    await writer.drain()


async def _open_client(endpoint: str) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
    host, port = _normalize_endpoint(endpoint)
    try:
        reader, writer = await asyncio.open_connection(host, port)
    except Exception as exc:  # noqa: BLE001
        raise GhidraBridgeError(f'连接 Ghidra backend 失败: {type(exc).__name__}: {exc}') from exc

    init_id = next(_REQUEST_IDS)
    await _send_request(
        writer,
        {
            'jsonrpc': '2.0',
            'id': init_id,
            'method': 'initialize',
            'params': {
                'protocolVersion': '2025-11-25',
                'capabilities': {},
                'clientInfo': {'name': 'android-reverse-mcp', 'version': '0.1.0'},
            },
        },
    )
    response = await _read_json_line(reader)
    if response.get('id') != init_id or 'error' in response:
        raise GhidraBridgeError(f'Ghidra backend initialize 失败: {response}')

    await _send_request(
        writer,
        {
            'jsonrpc': '2.0',
            'method': 'notifications/initialized',
            'params': {},
        },
    )
    return reader, writer


def _normalize_tool_result(tool_name: str, response: dict[str, Any]) -> dict[str, Any]:
    if 'error' in response:
        error = response.get('error') or {}
        return {
            'ok': False,
            'tool': tool_name,
            'error': f"{error.get('message', 'unknown error')}",
            'error_payload': error,
        }
    result = response.get('result') or {}
    structured = result.get('structuredContent')
    content_items = result.get('content') or []
    texts = [
        item.get('text', str(item))
        for item in content_items
        if isinstance(item, dict)
    ]
    return {
        'ok': True,
        'tool': tool_name,
        'payload': structured,
        'content': texts,
        'raw_result': result,
    }


async def call_tool(
    endpoint: str,
    tool_name: str,
    arguments: dict[str, Any] | None = None,
    *,
    timeout: int = 300,
) -> dict[str, Any]:
    reader: asyncio.StreamReader | None = None
    writer: asyncio.StreamWriter | None = None
    try:
        reader, writer = await asyncio.wait_for(_open_client(endpoint), timeout=timeout)
        request_id = next(_REQUEST_IDS)
        await asyncio.wait_for(
            _send_request(
                writer,
                {
                    'jsonrpc': '2.0',
                    'id': request_id,
                    'method': 'tools/call',
                    'params': {
                        'name': tool_name,
                        'arguments': arguments or {},
                    },
                },
            ),
            timeout=timeout,
        )
        response = await asyncio.wait_for(_read_json_line(reader), timeout=timeout)
        return _normalize_tool_result(tool_name, response)
    except Exception as exc:  # noqa: BLE001
        return {'ok': False, 'tool': tool_name, 'error': f'{type(exc).__name__}: {exc}'}
    finally:
        if writer is not None:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:  # noqa: BLE001
                pass


async def list_tools(endpoint: str, *, page_size: int = 64) -> dict[str, Any]:
    reader: asyncio.StreamReader | None = None
    writer: asyncio.StreamWriter | None = None
    try:
        reader, writer = await _open_client(endpoint)
        offset = 0
        tools: list[dict[str, Any]] = []
        while True:
            request_id = next(_REQUEST_IDS)
            await _send_request(
                writer,
                {
                    'jsonrpc': '2.0',
                    'id': request_id,
                    'method': 'tools/list',
                    'params': {'offset': offset, 'limit': page_size},
                },
            )
            response = await _read_json_line(reader)
            if 'error' in response:
                raise GhidraBridgeError(f'tools/list 失败: {response["error"]}')
            result = response.get('result') or {}
            page = result.get('tools') or []
            tools.extend(page)
            if not result.get('has_more'):
                break
            offset = int(result.get('next_offset', offset + len(page)))
        return {'ok': True, 'tools': tools, 'total': len(tools)}
    except Exception as exc:  # noqa: BLE001
        return {'ok': False, 'error': f'{type(exc).__name__}: {exc}'}
    finally:
        if writer is not None:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:  # noqa: BLE001
                pass
