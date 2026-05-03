from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from .base import NativeBackend, NativeCapabilitySet
from .client import call_tool, list_tools

_SHARED_TOOL_NAMES = frozenset(
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


@dataclass(frozen=True)
class IdaBackend(NativeBackend):
    url: str
    tool_mapping: Mapping[str, str] = field(default_factory=dict)

    capabilities = NativeCapabilitySet(
        shared_tools=_SHARED_TOOL_NAMES,
        extension_prefix="native_ida_",
    )

    @classmethod
    def backend_name(cls) -> str:
        return "ida"

    def _tool_name_for(self, operation: str) -> str:
        tool_name = self.tool_mapping.get(operation)
        if tool_name is None:
            raise RuntimeError(
                f"IDA backend tool mapping not configured for operation: {operation}"
            )
        return tool_name

    async def health(self) -> dict[str, Any]:
        result = await call_tool(self.url, self._tool_name_for("health"), {})
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
        return await call_tool(self.url, self._tool_name_for("list_sessions"), {})

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
        result = await call_tool(
            self.url,
            self._tool_name_for("open_program"),
            {
                "input_path": path,
                "run_auto_analysis": update_analysis,
            },
            timeout=1800,
        )
        payload = result.get("payload") or {}
        session = payload.get("session") if isinstance(payload, dict) else None
        if isinstance(session, dict) and "session_id" in session:
            result["session_id"] = session["session_id"]
        return result

    async def program_summary(self, *, session_id: str) -> dict[str, Any]:
        tool_name = self._tool_name_for("program_summary")
        arguments = {} if tool_name == "idalib_current" else {"session_id": session_id}
        return await call_tool(
            self.url,
            tool_name,
            arguments,
        )

    async def save_program(self, *, session_id: str) -> dict[str, Any]:
        return await call_tool(
            self.url,
            self._tool_name_for("save_program"),
            {"session_id": session_id},
            timeout=600,
        )

    async def list_functions(
        self,
        *,
        session_id: str,
        query: str | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> dict[str, Any]:
        arguments = {
            "queries": [{
                "offset": offset,
                "count": limit,
                "filter": query or "",
            }]
        }
        return await call_tool(
            self.url,
            self._tool_name_for("list_functions"),
            arguments,
            timeout=300,
        )

    async def decompile_function(self, *, session_id: str, function_start: str) -> dict[str, Any]:
        return await call_tool(
            self.url,
            self._tool_name_for("decompile_function"),
            {"addr": function_start},
            timeout=600,
        )

    async def function_report(self, *, session_id: str, function_start: str) -> dict[str, Any]:
        return await call_tool(
            self.url,
            self._tool_name_for("function_report"),
            {"queries": [{"addr": function_start}]},
            timeout=600,
        )

    async def xrefs_to(self, *, session_id: str, address: str, limit: int = 100) -> dict[str, Any]:
        return await call_tool(
            self.url,
            self._tool_name_for("xrefs_to"),
            {"addrs": [address], "limit": limit},
            timeout=300,
        )

    async def xrefs_from(self, *, session_id: str, address: str, limit: int = 100) -> dict[str, Any]:
        return await call_tool(
            self.url,
            self._tool_name_for("xrefs_from"),
            {
                "queries": [{
                    "addr": address,
                    "direction": "from",
                    "count": limit,
                }]
            },
            timeout=300,
        )

    async def rename_function(self, *, session_id: str, function_start: str, new_name: str) -> dict[str, Any]:
        return await call_tool(
            self.url,
            self._tool_name_for("rename_function"),
            {"batch": {"func": [{"addr": function_start, "name": new_name}]}},
            timeout=300,
        )

    async def list_variables(self, *, session_id: str, function_start: str) -> dict[str, Any]:
        return await call_tool(
            self.url,
            self._tool_name_for("list_variables"),
            {"addrs": [function_start]},
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
            self._tool_name_for("rename_variable"),
            {
                "batch": {
                    "local": [{"func_addr": function_start, "old": old_name, "new": new_name}],
                    "stack": [{"func_addr": function_start, "old": old_name, "new": new_name}],
                }
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
            self._tool_name_for("set_comment"),
            {"items": [{"addr": address, "comment": comment}]},
            timeout=300,
        )
