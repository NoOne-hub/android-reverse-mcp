import os
from typing import Mapping

from .base import NativeBackend, NativeBackendConfig
from .ghidra import GhidraBackend
from .ida import IdaBackend

DEFAULT_IDA_TOOL_MAPPING: dict[str, str] = {
    "health": "idalib_list",
    "list_sessions": "idalib_list",
    "open_program": "idalib_open",
    "program_summary": "idalib_current",
    "save_program": "idalib_save",
    "list_functions": "list_funcs",
    "decompile_function": "decompile",
    "function_report": "analyze_batch",
    "xrefs_to": "xrefs_to",
    "xrefs_from": "xref_query",
    "rename_function": "rename",
    "list_variables": "stack_frame",
    "rename_variable": "rename",
    "set_comment": "set_comments",
}


def parse_native_backend_config() -> NativeBackendConfig:
    name = os.environ.get("NATIVE_BACKEND")
    url = os.environ.get("NATIVE_BACKEND_URL")
    if name and url:
        return NativeBackendConfig(name=name, url=url)

    ghidra_url = os.environ.get("GHIDRA_BACKEND")
    if ghidra_url:
        return NativeBackendConfig(name="ghidra", url=ghidra_url)

    raise RuntimeError("native backend 未配置")


def create_native_backend(
    name: str,
    url: str,
    *,
    tool_mapping: Mapping[str, str] | None = None,
) -> NativeBackend:
    if name == GhidraBackend.backend_name():
        return GhidraBackend(url=url)
    if name == IdaBackend.backend_name():
        mapping = dict(DEFAULT_IDA_TOOL_MAPPING)
        if tool_mapping:
            mapping.update(tool_mapping)
        return IdaBackend(url=url, tool_mapping=mapping)
    raise ValueError(f"unsupported native backend: {name}")
