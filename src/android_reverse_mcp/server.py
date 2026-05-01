from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

from fastmcp import FastMCP

from . import backend_client
from .modules import apktool as apktool_mod
from .modules import diff_tool as diff_mod
from .modules import ghidra_bridge as ghidra_mod
from .modules import sign_tools as sign_mod
from .workspace import WorkspaceManager

logger = logging.getLogger("android-reverse-mcp")
if not logger.handlers:
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
    logger.addHandler(handler)
logger.setLevel(logging.INFO)
logger.propagate = False

mcp = FastMCP("Android Reverse MCP")
_workspace_manager: WorkspaceManager | None = None
_ghidra_backend: str | None = None


def _call(endpoint: str, **params):
    try:
        return backend_client.request(endpoint, params)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Backend call failed: %s", exc)
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def _workspace() -> WorkspaceManager:
    global _workspace_manager
    if _workspace_manager is None:
        root = os.environ.get("APK_MCP_WORKSPACE", str(Path.cwd() / "workspace"))
        _workspace_manager = WorkspaceManager(root)
    return _workspace_manager


def _utcnow() -> str:
    return datetime.now(UTC).isoformat()


def _workspace_project_or_none() -> dict | None:
    try:
        return _workspace().get_current_project()
    except Exception:
        return None


def _default_state_path(filename: str = "project-state.json") -> Path:
    project = _workspace().get_current_project()
    return _workspace().get_project_paths(project["project_id"]).state_dir / filename


def _save_state_file(path: Path) -> dict:
    project = _workspace_project_or_none()
    renames = _call("list-renames")
    if not renames.get("ok"):
        return renames
    current_jadx = _call("current-project")
    payload = {
        "version": 1,
        "saved_at": _utcnow(),
        "workspace_project": project,
        "jadx_project": current_jadx if current_jadx.get("ok") else None,
        "renames": renames.get("renames", []),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True, "state_path": str(path), "rename_count": len(payload["renames"]), "workspace_project_id": None if not project else project["project_id"]}


def _replay_rename_entry(entry: dict) -> dict:
    rename_type = entry.get("rename_type")
    decl_class_raw = entry.get("declaring_class_raw")
    short_id = entry.get("short_id")
    new_name = entry.get("new_name", "")
    if rename_type == "class":
        return _call("rename-class", class_name=decl_class_raw, new_name=new_name)
    if rename_type == "package":
        return _call("rename-package", old_package_name=decl_class_raw, new_package_name=new_name)
    if rename_type == "method":
        return _call(
            "rename-method",
            class_name=decl_class_raw,
            method_name=short_id,
            method_short_id=short_id,
            new_name=new_name,
        )
    if rename_type == "field":
        return _call(
            "rename-field",
            class_name=decl_class_raw,
            field_name=short_id,
            field_short_id=short_id,
            new_name=new_name,
        )
    if rename_type == "variable":
        code_ref_index = int(entry["code_ref_index"])
        reg = str(code_ref_index >> 16)
        ssa = str(code_ref_index & 0xFFFF)
        return _call(
            "rename-variable",
            class_name=decl_class_raw,
            method_name=short_id,
            method_short_id=short_id,
            variable_name=entry.get("variable_name", short_id),
            new_name=new_name,
            reg=reg,
            ssa=ssa,
        )
    return {"ok": False, "error": f"不支持的 rename_type: {rename_type}", "entry": entry}


def _auto_persist_state_if_possible() -> dict | None:
    try:
        return _save_state_file(_default_state_path())
    except Exception:
        return None


def _restore_state_file(path: Path, *, reload_apk: bool = True) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    workspace_project = data.get("workspace_project") or {}
    workspace_apk_path = workspace_project.get("workspace_apk_path")
    if reload_apk and workspace_apk_path:
        loaded = _call("load-apk", apk_path=workspace_apk_path)
        if not loaded.get("ok"):
            return {"ok": False, "stage": "load_apk", "state_path": str(path), "loaded": loaded}
    results = []
    for entry in data.get("renames", []):
        result = _replay_rename_entry(entry)
        results.append({"entry": entry, "result": result})
        if not result.get("ok"):
            return {"ok": False, "stage": "replay_rename", "state_path": str(path), "failed": {"entry": entry, "result": result}, "applied_count": len(results) - 1}
    return {"ok": True, "state_path": str(path), "rename_count": len(data.get("renames", [])), "results": results}


def _maybe_restore_saved_state() -> dict | None:
    try:
        path = _default_state_path()
    except Exception:
        return None
    if not path.is_file():
        return None
    try:
        return _restore_state_file(path, reload_apk=False)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "state_path": str(path), "error": f"{type(exc).__name__}: {exc}"}


@mcp.tool()
async def health() -> dict:
    """返回当前 headless MCP 与后端状态。"""
    return {
        "ok": True,
        "jadx_backend": backend_client.health_ping(),
        "workspace_root": str(_workspace().root),
        "workspace_projects": len(_workspace().list_projects()),
        "ghidra_backend": _ghidra_backend,
        "ghidra_enabled": bool(_ghidra_backend),
    }


@mcp.tool()
async def workspace_import_apk(apk_path: str) -> dict:
    """把 APK 导入统一工作区，后续 decode/build/sign/diff 都基于该工作区。"""
    try:
        return _workspace().import_apk(apk_path)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


@mcp.tool()
async def workspace_list_projects() -> dict:
    try:
        projects = _workspace().list_projects()
        return {"ok": True, "projects": projects, "total": len(projects)}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


@mcp.tool()
async def workspace_select_project(project_id: str) -> dict:
    try:
        project = _workspace().set_current_project(project_id)
        return {"ok": True, "project": project}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


@mcp.tool()
async def workspace_get_current_project() -> dict:
    try:
        return {"ok": True, "project": _workspace().get_current_project()}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


@mcp.tool()
async def list_output_files() -> dict:
    try:
        paths = _workspace().get_project_paths()
        files = []
        if paths.outputs_dir.exists():
            for path in sorted(paths.outputs_dir.rglob("*")):
                if path.is_file():
                    files.append(
                        {
                            "name": path.name,
                            "relative_path": path.relative_to(paths.outputs_dir).as_posix(),
                            "path": str(path),
                            "size": path.stat().st_size,
                            "mtime": datetime.fromtimestamp(path.stat().st_mtime, tz=UTC).isoformat(),
                        }
                    )
        return {"ok": True, "project_id": paths.root.name, "outputs_dir": str(paths.outputs_dir), "files": files, "total": len(files)}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


@mcp.tool()
async def export_project_state(state_name: str = "project-state.json") -> dict:
    try:
        return _save_state_file(_default_state_path(state_name))
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


@mcp.tool()
async def import_project_state(state_name: str = "project-state.json", reload_apk: bool = True) -> dict:
    try:
        return _restore_state_file(_default_state_path(state_name), reload_apk=reload_apk)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


@mcp.tool()
async def prepare_single_apk_workspace(apk_path: str, decode: bool = True, load_to_jadx: bool = True) -> dict:
    """一键导入工作区，可选 decode，并加载到 JADX 语义后端。"""
    try:
        imported = _workspace().import_apk(apk_path)
        result: dict = {"ok": True, "workspace": imported}
        if decode:
            result["decode"] = apktool_mod.decode_current_project(_workspace())
            if not result["decode"].get("ok"):
                result["ok"] = False
        if load_to_jadx:
            result["jadx"] = _call("load-apk", apk_path=imported["workspace_apk_path"])
            if not result["jadx"].get("ok"):
                result["ok"] = False
            else:
                restored = _maybe_restore_saved_state()
                if restored is not None:
                    result["restored_state"] = restored
                    if not restored.get("ok"):
                        result["ok"] = False
        return result
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


@mcp.tool()
async def load_apk(apk_path: str) -> dict:
    """加载并分析指定 APK。"""
    return _call("load-apk", apk_path=apk_path)


@mcp.tool()
async def list_projects() -> dict:
    """列出当前后端可见项目。当前单容器模式通常只有一个。"""
    return _call("list-projects")


@mcp.tool()
async def select_project(project_id: str) -> dict:
    """当前 headless 后端为单项目模式，此接口保留兼容。"""
    return _call("select-project", project_id=project_id)


@mcp.tool()
async def get_current_project() -> dict:
    """返回当前活跃项目摘要。"""
    return _call("current-project")


@mcp.tool()
async def fetch_current_class() -> dict:
    """Headless 模式无 GUI 焦点，降级为返回 main activity。"""
    return _call("main-activity")


@mcp.tool()
async def get_selected_text() -> dict:
    """Headless 模式无选中文本。"""
    return {"ok": False, "tool": "get_selected_text", "error": "headless 模式无选中文本"}


@mcp.tool()
async def get_all_classes(offset: int = 0, count: int = 0) -> dict:
    return _call("all-classes", offset=offset, count=count)


@mcp.tool()
async def get_class_source(class_name: str) -> dict:
    return _call("class-source", class_name=class_name)


@mcp.tool()
async def get_methods_of_class(class_name: str) -> dict:
    return _call("methods-of-class", class_name=class_name)


@mcp.tool()
async def get_fields_of_class(class_name: str) -> dict:
    return _call("fields-of-class", class_name=class_name)


@mcp.tool()
async def get_method_by_name(class_name: str, method_name: str) -> dict:
    return _call("method-by-name", class_name=class_name, method_name=method_name)


@mcp.tool()
async def search_method_by_name(method_name: str) -> dict:
    return _call("search-method", method_name=method_name)


@mcp.tool()
async def search_classes_by_keyword(
    search_term: str,
    package: str = "",
    search_in: str = "code",
    offset: int = 0,
    count: int = 20,
) -> dict:
    return _call("search-classes", search_term=search_term, package=package, search_in=search_in, offset=offset, count=count)


@mcp.tool()
async def get_smali_of_class(class_name: str) -> dict:
    return _call("smali-of-class", class_name=class_name)


@mcp.tool()
async def get_android_manifest() -> dict:
    return _call("manifest")


@mcp.tool()
async def get_manifest_component(component_type: str, only_exported: bool = False) -> dict:
    return _call("manifest-component", component_type=component_type, only_exported=str(only_exported).lower())


@mcp.tool()
async def get_strings(offset: int = 0, count: int = 0) -> dict:
    return _call("strings", offset=offset, count=count)


@mcp.tool()
async def get_all_resource_file_names(offset: int = 0, count: int = 0) -> dict:
    return _call("list-all-resource-files-names", offset=offset, count=count)


@mcp.tool()
async def get_resource_file(resource_name: str) -> dict:
    return _call("get-resource-file", file_name=resource_name)


@mcp.tool()
async def get_main_application_classes_names() -> dict:
    return _call("main-application-classes-names")


@mcp.tool()
async def get_main_application_classes_code(offset: int = 0, count: int = 0) -> dict:
    return _call("main-application-classes-code", offset=offset, count=count)


@mcp.tool()
async def get_main_activity_class() -> dict:
    return _call("main-activity")


@mcp.tool()
async def get_package_tree() -> dict:
    return _call("package-tree")


@mcp.tool()
async def get_cache_stats() -> dict:
    """语义后端不再暴露文件缓存统计，这里返回后端健康信息。"""
    return backend_client.health_ping()


@mcp.tool()
async def clear_cache() -> dict:
    """当前版本没有额外文件缓存可清；保留兼容接口。"""
    return {"ok": True, "cleared_cached_files": 0, "message": "semantic backend 无额外文本缓存"}


@mcp.tool()
async def get_xrefs_to_class(class_name: str, offset: int = 0, count: int = 20) -> dict:
    return _call("xrefs-to-class", class_name=class_name, offset=offset, count=count)


@mcp.tool()
async def get_xrefs_to_method(class_name: str, method_name: str, offset: int = 0, count: int = 20) -> dict:
    return _call("xrefs-to-method", class_name=class_name, method_name=method_name, offset=offset, count=count)


@mcp.tool()
async def get_xrefs_to_field(class_name: str, field_name: str, offset: int = 0, count: int = 20) -> dict:
    return _call("xrefs-to-field", class_name=class_name, field_name=field_name, offset=offset, count=count)


@mcp.tool()
async def rename_class(class_name: str, new_name: str) -> dict:
    result = _call("rename-class", class_name=class_name, new_name=new_name)
    if result.get("ok"):
        result["state_saved"] = _auto_persist_state_if_possible()
    return result


@mcp.tool()
async def rename_method(method_name: str, new_name: str, class_name: str | None = None, method_short_id: str | None = None) -> dict:
    result = _call("rename-method", class_name=class_name, method_name=method_name, method_short_id=method_short_id, new_name=new_name)
    if result.get("ok"):
        result["state_saved"] = _auto_persist_state_if_possible()
    return result


@mcp.tool()
async def rename_field(class_name: str, field_name: str, new_name: str, field_short_id: str | None = None) -> dict:
    result = _call("rename-field", class_name=class_name, field_name=field_name, field_short_id=field_short_id, new_name=new_name)
    if result.get("ok"):
        result["state_saved"] = _auto_persist_state_if_possible()
    return result


@mcp.tool()
async def rename_package(old_package_name: str, new_package_name: str) -> dict:
    result = _call("rename-package", old_package_name=old_package_name, new_package_name=new_package_name)
    if result.get("ok"):
        result["state_saved"] = _auto_persist_state_if_possible()
    return result


@mcp.tool()
async def rename_variable(
    class_name: str,
    method_name: str,
    variable_name: str,
    new_name: str,
    reg: str | None = None,
    ssa: str | None = None,
    method_short_id: str | None = None,
) -> dict:
    result = _call(
        "rename-variable",
        class_name=class_name,
        method_name=method_name,
        method_short_id=method_short_id,
        variable_name=variable_name,
        new_name=new_name,
        reg=reg,
        ssa=ssa,
    )
    if result.get("ok"):
        result["state_saved"] = _auto_persist_state_if_possible()
    return result


@mcp.tool()
async def list_renames() -> dict:
    return _call("list-renames")


@mcp.tool()
async def get_method_variables(class_name: str, method_name: str, method_short_id: str | None = None) -> dict:
    return _call("method-variables", class_name=class_name, method_name=method_name, method_short_id=method_short_id)


@mcp.tool()
async def apktool_decode_current(force: bool = False, use_aapt2: bool = False) -> dict:
    try:
        return apktool_mod.decode_current_project(_workspace(), force=force, use_aapt2=use_aapt2)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


@mcp.tool()
async def apktool_reset_current() -> dict:
    try:
        return _workspace().reset_current_from_baseline()
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


@mcp.tool()
async def apktool_list_current_files(prefix: str = "", from_baseline: bool = False) -> dict:
    try:
        return apktool_mod.list_decoded_files(_workspace(), prefix=prefix, from_baseline=from_baseline)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


@mcp.tool()
async def apktool_read_file(relative_path: str, from_baseline: bool = False) -> dict:
    try:
        return apktool_mod.read_decoded_file(_workspace(), relative_path, from_baseline=from_baseline)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


@mcp.tool()
async def apktool_write_file(relative_path: str, content: str) -> dict:
    try:
        return apktool_mod.write_decoded_file(_workspace(), relative_path, content)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


@mcp.tool()
async def apktool_build_current(output_name: str = "unsigned-current.apk", use_aapt2: bool = False) -> dict:
    try:
        return apktool_mod.build_current_project(_workspace(), output_name=output_name, use_aapt2=use_aapt2)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


@mcp.tool()
async def load_rebuilt_apk_to_jadx(apk_path: str | None = None, preferred_name: str = "signed-current.apk") -> dict:
    try:
        if apk_path is None:
            paths = _workspace().get_project_paths()
            candidate = paths.outputs_dir / preferred_name
            if candidate.is_file():
                apk_path = str(candidate)
            else:
                apk_candidates = sorted(paths.outputs_dir.glob("*.apk"), key=lambda p: p.stat().st_mtime, reverse=True)
                if not apk_candidates:
                    return {"ok": False, "error": "outputs 目录里没有可加载的 APK，请先 build/sign"}
                apk_path = str(apk_candidates[0])
        result = _call("load-apk", apk_path=apk_path)
        if result.get("ok"):
            restored = _maybe_restore_saved_state()
            if restored is not None:
                result["restored_state"] = restored
        result["loaded_apk_path"] = apk_path
        return result
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


@mcp.tool()
async def sign_generate_debug_keystore(
    keystore_name: str = "debug.keystore",
    alias: str = "androiddebugkey",
    storepass: str = "android",
    keypass: str = "android",
) -> dict:
    try:
        return sign_mod.generate_debug_keystore(_workspace(), keystore_name=keystore_name, alias=alias, storepass=storepass, keypass=keypass)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


@mcp.tool()
async def sign_zipalign_apk(apk_path: str, output_name: str = "aligned.apk") -> dict:
    try:
        return sign_mod.zipalign_apk(_workspace(), apk_path, output_name=output_name)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


@mcp.tool()
async def sign_apk(
    apk_path: str,
    output_name: str = "signed.apk",
    keystore_path: str | None = None,
    alias: str = "androiddebugkey",
    storepass: str = "android",
    keypass: str = "android",
) -> dict:
    try:
        return sign_mod.sign_apk(
            _workspace(),
            apk_path,
            output_name=output_name,
            keystore_path=keystore_path,
            alias=alias,
            storepass=storepass,
            keypass=keypass,
        )
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


@mcp.tool()
async def sign_verify_apk_signature(apk_path: str) -> dict:
    try:
        return sign_mod.verify_apk_signature(apk_path)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


@mcp.tool()
async def rebuild_and_sign_current_apk(
    unsigned_name: str = "unsigned-current.apk",
    aligned_name: str = "aligned-current.apk",
    signed_name: str = "signed-current.apk",
) -> dict:
    try:
        build = apktool_mod.build_current_project(_workspace(), output_name=unsigned_name)
        if not build.get("ok"):
            return {"ok": False, "stage": "build", "build": build}
        keystore = sign_mod.generate_debug_keystore(_workspace())
        if not keystore.get("ok"):
            return {"ok": False, "stage": "keystore", "keystore": keystore}
        aligned = sign_mod.zipalign_apk(_workspace(), build["output_apk"], output_name=aligned_name)
        if not aligned.get("ok"):
            return {"ok": False, "stage": "zipalign", "build": build, "aligned": aligned}
        signed = sign_mod.sign_apk(_workspace(), aligned["output_apk"], output_name=signed_name)
        if not signed.get("ok"):
            return {"ok": False, "stage": "sign", "build": build, "aligned": aligned, "signed": signed}
        verify = sign_mod.verify_apk_signature(signed["output_apk"])
        return {"ok": verify.get("ok", False), "build": build, "keystore": keystore, "aligned": aligned, "signed": signed, "verify": verify}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


@mcp.tool()
async def diff_workspace_changes() -> dict:
    try:
        return diff_mod.diff_workspace_changes(_workspace())
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


@mcp.tool()
async def diff_decoded_file(relative_path: str, context: int = 3) -> dict:
    try:
        return diff_mod.diff_decoded_file(_workspace(), relative_path, context=context)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def _require_ghidra_backend() -> str:
    if not _ghidra_backend:
        raise RuntimeError('Ghidra backend 未配置，请设置 --ghidra-backend 或 GHIDRA_BACKEND')
    return _ghidra_backend


@mcp.tool()
async def ghidra_list_remote_tools() -> dict:
    """列出远端 ghidra-headless-mcp 暴露的 tools，用于排查联通情况。"""
    try:
        return await ghidra_mod.list_tools(_require_ghidra_backend())
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


@mcp.tool()
async def ghidra_health() -> dict:
    """探测 Ghidra backend 当前状态；即使尚未打开 so，也可用于检查联通。"""
    try:
        result = await ghidra_mod.call_tool(_require_ghidra_backend(), 'health.ping', {})
        result['ghidra_backend'] = _ghidra_backend
        return result
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


@mcp.tool()
async def ghidra_list_sessions() -> dict:
    try:
        return await ghidra_mod.call_tool(_require_ghidra_backend(), 'program.list_open', {})
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


@mcp.tool()
async def ghidra_program_summary(session_id: str) -> dict:
    try:
        return await ghidra_mod.call_tool(_require_ghidra_backend(), 'program.summary', {'session_id': session_id})
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


@mcp.tool()
async def ghidra_save_program(session_id: str) -> dict:
    """保存当前 Ghidra program 到项目数据库。"""
    try:
        return await ghidra_mod.call_tool(_require_ghidra_backend(), 'program.save', {'session_id': session_id}, timeout=600)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


@mcp.tool()
async def list_native_libraries(from_baseline: bool = False) -> dict:
    """列出当前 APK 工作区里的 native so。优先从 decode 目录读取；未 decode 时回退到原 APK zip。"""
    try:
        return _workspace().list_native_libraries(from_baseline=from_baseline)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


@mcp.tool()
async def open_native_library(relative_path: str, run_auto_analysis: bool = True, from_baseline: bool = False) -> dict:
    """把指定 so 送给 Ghidra backend 打开分析。"""
    try:
        materialized = _workspace().materialize_native_library(relative_path, from_baseline=from_baseline)
        session_root = _workspace().get_ghidra_session_root(relative_path)
        result = await ghidra_mod.call_tool(
            _require_ghidra_backend(),
            'program.open',
            {
                'path': str(materialized),
                'read_only': False,
                'update_analysis': run_auto_analysis,
                'project_location': str(session_root),
                'project_name': 'ghidra',
                'program_name': Path(relative_path).name,
            },
            timeout=1800,
        )
        result['library'] = {
            'relative_path': relative_path,
            'materialized_path': str(materialized),
            'from_baseline': from_baseline,
            'ghidra_project_root': str(session_root),
        }
        payload = result.get('payload') or {}
        if isinstance(payload, dict):
            if 'session_id' in payload:
                result['session_id'] = payload['session_id']
            if 'project_location' in payload:
                result['project_location'] = payload['project_location']
        return result
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


@mcp.tool()
async def ghidra_list_functions(session_id: str, query: str | None = None, offset: int = 0, limit: int = 50) -> dict:
    try:
        arguments = {'session_id': session_id, 'offset': offset, 'limit': limit}
        if query:
            arguments['query'] = query
        return await ghidra_mod.call_tool(_require_ghidra_backend(), 'function.list', arguments, timeout=300)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


@mcp.tool()
async def ghidra_decompile_function(session_id: str, function_start: str) -> dict:
    try:
        return await ghidra_mod.call_tool(
            _require_ghidra_backend(),
            'decomp.function',
            {'session_id': session_id, 'function_start': function_start},
            timeout=600,
        )
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


@mcp.tool()
async def ghidra_function_report(session_id: str, function_start: str) -> dict:
    try:
        return await ghidra_mod.call_tool(
            _require_ghidra_backend(),
            'function.report',
            {'session_id': session_id, 'function_start': function_start},
            timeout=600,
        )
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


@mcp.tool()
async def ghidra_xrefs_to(session_id: str, address: str, limit: int = 100) -> dict:
    try:
        return await ghidra_mod.call_tool(
            _require_ghidra_backend(),
            'reference.to',
            {'session_id': session_id, 'address': address, 'limit': limit},
            timeout=300,
        )
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


@mcp.tool()
async def ghidra_xrefs_from(session_id: str, address: str, limit: int = 100) -> dict:
    try:
        return await ghidra_mod.call_tool(
            _require_ghidra_backend(),
            'reference.from',
            {'session_id': session_id, 'address': address, 'limit': limit},
            timeout=300,
        )
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


@mcp.tool()
async def ghidra_rename_function(session_id: str, function_start: str, new_name: str) -> dict:
    try:
        return await ghidra_mod.call_tool(
            _require_ghidra_backend(),
            'function.rename',
            {'session_id': session_id, 'function_start': function_start, 'name': new_name},
            timeout=300,
        )
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


@mcp.tool()
async def ghidra_list_variables(session_id: str, function_start: str) -> dict:
    try:
        return await ghidra_mod.call_tool(
            _require_ghidra_backend(),
            'function.variables',
            {'session_id': session_id, 'function_start': function_start},
            timeout=300,
        )
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


@mcp.tool()
async def ghidra_rename_variable(session_id: str, function_start: str, old_name: str, new_name: str) -> dict:
    try:
        return await ghidra_mod.call_tool(
            _require_ghidra_backend(),
            'variable.rename',
            {'session_id': session_id, 'function_start': function_start, 'name': old_name, 'new_name': new_name},
            timeout=300,
        )
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


@mcp.tool()
async def ghidra_set_comment(
    session_id: str,
    address: str,
    comment: str,
    *,
    scope: str = 'listing',
    comment_type: str = 'eol',
) -> dict:
    try:
        return await ghidra_mod.call_tool(
            _require_ghidra_backend(),
            'comment.set',
            {
                'session_id': session_id,
                'address': address,
                'scope': scope,
                'comment_type': comment_type,
                'comment': comment,
            },
            timeout=300,
        )
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}




@mcp.tool()
async def debug_get_stack_frames() -> dict:
    return _call("debug/stack-frames")


@mcp.tool()
async def debug_get_threads() -> dict:
    return _call("debug/threads")


@mcp.tool()
async def debug_get_variables() -> dict:
    return _call("debug/variables")


def main() -> None:
    parser = argparse.ArgumentParser("Android Reverse MCP Server")
    parser.add_argument("--http", action="store_true", default=False, help="以 streamable-http 运行")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8651)
    parser.add_argument("--backend-url", default=os.environ.get("JADX_BACKEND_URL"))
    parser.add_argument("--backend-host", default=os.environ.get("JADX_BACKEND_HOST", "127.0.0.1"))
    parser.add_argument("--backend-port", type=int, default=int(os.environ.get("JADX_BACKEND_PORT", "8650")))
    parser.add_argument("--apk", default=os.environ.get("TARGET_APK"))
    parser.add_argument("--threads", type=int, default=int(os.environ.get("JADX_THREADS", str(max(2, os.cpu_count() or 2)))))
    parser.add_argument("--workspace", default=os.environ.get("APK_MCP_WORKSPACE", str(Path.cwd() / "workspace")))
    parser.add_argument("--decode-on-start", action="store_true", default=os.environ.get("DECODE_ON_START", "").lower() in {"1", "true", "yes"})
    parser.add_argument("--ghidra-backend", default=os.environ.get("GHIDRA_BACKEND"))
    parser.add_argument(
        "--backend-jar",
        default=os.environ.get("JADX_BACKEND_JAR", str(Path(__file__).resolve().parents[2] / "java-backend" / "target" / "headless-jadx-backend-0.1.0.jar")),
    )
    parser.add_argument(
        "--jadx-jar",
        default=os.environ.get("JADX_ALL_JAR", str(Path(__file__).resolve().parents[2] / "java-backend" / "lib" / "jadx-1.5.5-all.jar")),
    )
    args = parser.parse_args()
    global _workspace_manager, _ghidra_backend
    _workspace_manager = WorkspaceManager(args.workspace)
    _ghidra_backend = args.ghidra_backend
    imported_workspace = None
    if args.apk:
        try:
            imported_workspace = _workspace_manager.import_apk(args.apk)
            if args.decode_on_start:
                decode_result = apktool_mod.decode_current_project(_workspace_manager)
                if not decode_result.get("ok"):
                    logger.warning("decode_on_start failed: %s", decode_result)
        except Exception as exc:  # noqa: BLE001
            logger.warning("workspace import failed for %s: %s", args.apk, exc)

    if args.backend_url:
        backend_client.set_backend_base(args.backend_url)
    else:
        backend_client.set_backend_base(f"http://{args.backend_host}:{args.backend_port}")
        backend_client.start_backend(
            backend_host=args.backend_host,
            backend_port=args.backend_port,
            backend_jar=args.backend_jar,
            jadx_jar=args.jadx_jar,
            apk_path=args.apk,
            threads=args.threads,
        )
    if imported_workspace and args.apk:
        restored = _maybe_restore_saved_state()
        if restored is not None:
            logger.info("restored_state=%s", restored)

    logger.info("mcp=%s:%s backend=%s workspace=%s project=%s", args.host, args.port, backend_client.get_backend_base(), args.workspace, imported_workspace["project_id"] if imported_workspace else None)
    if args.http:
        mcp.run(transport="streamable-http", host=args.host, port=args.port)
    else:
        mcp.run()


if __name__ == "__main__":
    main()
