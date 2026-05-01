from __future__ import annotations

import difflib
from pathlib import Path

from ..workspace import WorkspaceManager


def diff_workspace_changes(workspace: WorkspaceManager, *, project_id: str | None = None) -> dict:
    paths = workspace.get_project_paths(project_id)
    baseline = paths.baseline_dir
    current = paths.current_dir
    if not baseline.exists() or not current.exists():
        raise FileNotFoundError("baseline/current 目录不存在，请先 decode")

    base_files = {p.relative_to(baseline).as_posix() for p in baseline.rglob("*") if p.is_file()}
    current_files = {p.relative_to(current).as_posix() for p in current.rglob("*") if p.is_file()}

    added = sorted(current_files - base_files)
    deleted = sorted(base_files - current_files)
    maybe_changed = sorted(base_files & current_files)
    changed: list[str] = []
    unchanged_count = 0
    for rel in maybe_changed:
        if (baseline / rel).read_bytes() != (current / rel).read_bytes():
            changed.append(rel)
        else:
            unchanged_count += 1
    return {
        "ok": True,
        "project_id": paths.root.name,
        "added": added,
        "deleted": deleted,
        "changed": changed,
        "unchanged_count": unchanged_count,
        "total_changed": len(added) + len(deleted) + len(changed),
    }


def diff_decoded_file(workspace: WorkspaceManager, rel_path: str, *, project_id: str | None = None, context: int = 3) -> dict:
    paths = workspace.get_project_paths(project_id)
    left = workspace.resolve_baseline_path(rel_path, project_id)
    right = workspace.resolve_current_path(rel_path, project_id)
    left_text = left.read_text(encoding="utf-8") if left.exists() else ""
    right_text = right.read_text(encoding="utf-8") if right.exists() else ""
    diff = list(
        difflib.unified_diff(
            left_text.splitlines(),
            right_text.splitlines(),
            fromfile=f"baseline/{rel_path}",
            tofile=f"current/{rel_path}",
            lineterm="",
            n=context,
        )
    )
    return {
        "ok": True,
        "project_id": paths.root.name,
        "relative_path": rel_path,
        "baseline_exists": left.exists(),
        "current_exists": right.exists(),
        "diff": "\n".join(diff),
        "changed": left_text != right_text,
    }


def diff_texts(left_text: str, right_text: str, *, left_name: str = "left", right_name: str = "right", context: int = 3) -> dict:
    diff = list(
        difflib.unified_diff(
            left_text.splitlines(),
            right_text.splitlines(),
            fromfile=left_name,
            tofile=right_name,
            lineterm="",
            n=context,
        )
    )
    return {
        "ok": True,
        "changed": left_text != right_text,
        "diff": "\n".join(diff),
    }
