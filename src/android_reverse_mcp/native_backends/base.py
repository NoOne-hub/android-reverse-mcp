from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class NativeBackendConfig:
    name: str
    url: str


@dataclass(frozen=True)
class NativeCapabilitySet:
    shared_tools: frozenset[str]
    extension_prefix: str


class NativeBackend(Protocol):
    url: str
    capabilities: NativeCapabilitySet

    @classmethod
    def backend_name(cls) -> str: ...

    async def health(self) -> dict[str, Any]: ...

    async def list_remote_tools(self) -> dict[str, Any]: ...

    async def list_sessions(self) -> dict[str, Any]: ...

    async def open_program(
        self,
        *,
        path: str,
        read_only: bool = False,
        update_analysis: bool = True,
        project_location: str | None = None,
        project_name: str | None = None,
        program_name: str | None = None,
    ) -> dict[str, Any]: ...

    async def program_summary(self, *, session_id: str) -> dict[str, Any]: ...

    async def save_program(self, *, session_id: str) -> dict[str, Any]: ...

    async def list_functions(
        self,
        *,
        session_id: str,
        query: str | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> dict[str, Any]: ...

    async def decompile_function(self, *, session_id: str, function_start: str) -> dict[str, Any]: ...

    async def function_report(self, *, session_id: str, function_start: str) -> dict[str, Any]: ...

    async def xrefs_to(self, *, session_id: str, address: str, limit: int = 100) -> dict[str, Any]: ...

    async def xrefs_from(self, *, session_id: str, address: str, limit: int = 100) -> dict[str, Any]: ...

    async def rename_function(self, *, session_id: str, function_start: str, new_name: str) -> dict[str, Any]: ...

    async def list_variables(self, *, session_id: str, function_start: str) -> dict[str, Any]: ...

    async def rename_variable(
        self,
        *,
        session_id: str,
        function_start: str,
        old_name: str,
        new_name: str,
    ) -> dict[str, Any]: ...

    async def set_comment(
        self,
        *,
        session_id: str,
        address: str,
        comment: str,
        scope: str = "listing",
        comment_type: str = "eol",
    ) -> dict[str, Any]: ...
