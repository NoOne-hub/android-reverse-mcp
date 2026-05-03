from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .base import NativeBackend, NativeCapabilitySet
from .client import call_tool, list_tools


@dataclass(frozen=True)
class GhidraBackend(NativeBackend):
    url: str

    capabilities = NativeCapabilitySet(
        shared_tools=frozenset(
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
        ),
        extension_prefix="native_ghidra_",
    )

    @classmethod
    def backend_name(cls) -> str:
        return "ghidra"

    async def health(self) -> dict[str, Any]:
        result = await call_tool(self.url, "health.ping", {})
        result["backend"] = self.backend_name()
        result["backend_url"] = self.url
        return result

    async def list_remote_tools(self) -> dict[str, Any]:
        result = await list_tools(self.url)
        if result.get("ok"):
            result["backend"] = self.backend_name()
            result["backend_url"] = self.url
        return result

    async def list_sessions(self) -> dict[str, Any]:
        return await call_tool(self.url, "program.list_open", {})

    async def open_program(
        self,
        *,
        path: str,
        read_only: bool = False,
        update_analysis: bool = True,
        project_location: str | None = None,
        project_name: str | None = None,
        program_name: str | None = None,
    ) -> dict[str, Any]:
        arguments = {
            "path": path,
            "read_only": read_only,
            "update_analysis": update_analysis,
        }
        if project_location is not None:
            arguments["project_location"] = project_location
        if project_name is not None:
            arguments["project_name"] = project_name
        if program_name is not None:
            arguments["program_name"] = program_name

        result = await call_tool(self.url, "program.open", arguments, timeout=1800)
        payload = result.get("payload") or {}
        if isinstance(payload, dict):
            if "session_id" in payload:
                result["session_id"] = payload["session_id"]
            if "project_location" in payload:
                result["project_location"] = payload["project_location"]
        return result

    async def program_summary(self, *, session_id: str) -> dict[str, Any]:
        return await call_tool(self.url, "program.summary", {"session_id": session_id})

    async def save_program(self, *, session_id: str) -> dict[str, Any]:
        return await call_tool(self.url, "program.save", {"session_id": session_id}, timeout=600)

    async def list_functions(
        self,
        *,
        session_id: str,
        query: str | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> dict[str, Any]:
        arguments = {"session_id": session_id, "offset": offset, "limit": limit}
        if query:
            arguments["query"] = query
        return await call_tool(self.url, "function.list", arguments, timeout=300)

    async def decompile_function(self, *, session_id: str, function_start: str) -> dict[str, Any]:
        return await call_tool(
            self.url,
            "decomp.function",
            {"session_id": session_id, "function_start": function_start},
            timeout=600,
        )

    async def function_report(self, *, session_id: str, function_start: str) -> dict[str, Any]:
        return await call_tool(
            self.url,
            "function.report",
            {"session_id": session_id, "function_start": function_start},
            timeout=600,
        )

    async def xrefs_to(self, *, session_id: str, address: str, limit: int = 100) -> dict[str, Any]:
        return await call_tool(
            self.url,
            "reference.to",
            {"session_id": session_id, "address": address, "limit": limit},
            timeout=300,
        )

    async def xrefs_from(self, *, session_id: str, address: str, limit: int = 100) -> dict[str, Any]:
        return await call_tool(
            self.url,
            "reference.from",
            {"session_id": session_id, "address": address, "limit": limit},
            timeout=300,
        )

    async def rename_function(self, *, session_id: str, function_start: str, new_name: str) -> dict[str, Any]:
        return await call_tool(
            self.url,
            "function.rename",
            {"session_id": session_id, "function_start": function_start, "name": new_name},
            timeout=300,
        )

    async def list_variables(self, *, session_id: str, function_start: str) -> dict[str, Any]:
        return await call_tool(
            self.url,
            "function.variables",
            {"session_id": session_id, "function_start": function_start},
            timeout=300,
        )

    async def rename_variable(
        self,
        *,
        session_id: str,
        function_start: str,
        old_name: str,
        new_name: str,
    ) -> dict[str, Any]:
        return await call_tool(
            self.url,
            "variable.rename",
            {
                "session_id": session_id,
                "function_start": function_start,
                "name": old_name,
                "new_name": new_name,
            },
            timeout=300,
        )

    async def set_comment(
        self,
        *,
        session_id: str,
        address: str,
        comment: str,
        scope: str = "listing",
        comment_type: str = "eol",
    ) -> dict[str, Any]:
        return await call_tool(
            self.url,
            "comment.set",
            {
                "session_id": session_id,
                "address": address,
                "scope": scope,
                "comment_type": comment_type,
                "comment": comment,
            },
            timeout=300,
        )
