from __future__ import annotations

import shutil
from pathlib import Path

from ..workspace import WorkspaceManager
from .commands import ensure_command, run_command


def decode_current_project(
    workspace: WorkspaceManager,
    *,
    force: bool = False,
    use_aapt2: bool = False,
    project_id: str | None = None,
) -> dict:
    apktool_bin = ensure_command("apktool")
    paths = workspace.ensure_decoded_tree(project_id)
    if force:
        shutil.rmtree(paths.baseline_dir, ignore_errors=True)
        shutil.rmtree(paths.current_dir, ignore_errors=True)
        paths.baseline_dir.mkdir(parents=True, exist_ok=True)
        paths.current_dir.mkdir(parents=True, exist_ok=True)

    if any(paths.baseline_dir.iterdir()):
        baseline_status = {"ok": True, "skipped": True, "dir": str(paths.baseline_dir)}
    else:
        cmd = [apktool_bin, "d", "-f", "-o", str(paths.baseline_dir), str(paths.original_apk)]
        if use_aapt2:
            cmd.insert(2, "--use-aapt2")
        baseline_status = run_command(cmd)
        baseline_status["dir"] = str(paths.baseline_dir)
        if not baseline_status["ok"]:
            return {"ok": False, "stage": "decode_baseline", **baseline_status}

    if any(paths.current_dir.iterdir()):
        current_status = {"ok": True, "skipped": True, "dir": str(paths.current_dir)}
    else:
        shutil.copytree(paths.baseline_dir, paths.current_dir, dirs_exist_ok=True)
        current_status = {"ok": True, "copied_from_baseline": True, "dir": str(paths.current_dir)}

    return {
        "ok": True,
        "project_id": paths.root.name,
        "original_apk": str(paths.original_apk),
        "baseline_dir": str(paths.baseline_dir),
        "current_dir": str(paths.current_dir),
        "baseline": baseline_status,
        "current": current_status,
    }


def build_current_project(
    workspace: WorkspaceManager,
    *,
    output_name: str = "unsigned-current.apk",
    use_aapt2: bool = False,
    project_id: str | None = None,
) -> dict:
    apktool_bin = ensure_command("apktool")
    paths = workspace.ensure_decoded_tree(project_id)
    if not paths.current_dir.exists():
        raise FileNotFoundError("current 解包目录不存在，请先 decode")
    out_path = workspace.make_output_path(output_name, project_id)
    cmd = [apktool_bin, "b", str(paths.current_dir), "-o", str(out_path)]
    if use_aapt2:
        cmd.insert(2, "--use-aapt2")
    result = run_command(cmd)
    result.update(
        {
            "project_id": paths.root.name,
            "current_dir": str(paths.current_dir),
            "output_apk": str(out_path),
        }
    )
    return result


def read_decoded_file(workspace: WorkspaceManager, rel_path: str, *, from_baseline: bool = False, project_id: str | None = None) -> dict:
    file_path = workspace.resolve_baseline_path(rel_path, project_id) if from_baseline else workspace.resolve_current_path(rel_path, project_id)
    if not file_path.is_file():
        raise FileNotFoundError(f"文件不存在: {rel_path}")
    text = file_path.read_text(encoding="utf-8")
    return {
        "ok": True,
        "project_id": workspace.get_project_paths(project_id).root.name,
        "relative_path": rel_path,
        "from_baseline": from_baseline,
        "content": text,
        "line_count": len(text.splitlines()),
    }


def write_decoded_file(workspace: WorkspaceManager, rel_path: str, content: str, *, project_id: str | None = None) -> dict:
    file_path = workspace.resolve_current_path(rel_path, project_id)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content, encoding="utf-8")
    return {
        "ok": True,
        "project_id": workspace.get_project_paths(project_id).root.name,
        "relative_path": rel_path,
        "bytes_written": len(content.encode("utf-8")),
    }


def list_decoded_files(
    workspace: WorkspaceManager,
    *,
    prefix: str = "",
    from_baseline: bool = False,
    project_id: str | None = None,
) -> dict:
    paths = workspace.get_project_paths(project_id)
    base = paths.baseline_dir if from_baseline else paths.current_dir
    if not base.exists():
        raise FileNotFoundError("解包目录不存在，请先 decode")
    files: list[str] = []
    for path in sorted(base.rglob("*")):
        if path.is_file():
            rel = path.relative_to(base).as_posix()
            if prefix and not rel.startswith(prefix):
                continue
            files.append(rel)
    return {
        "ok": True,
        "project_id": paths.root.name,
        "from_baseline": from_baseline,
        "prefix": prefix,
        "files": files,
        "total": len(files),
    }
