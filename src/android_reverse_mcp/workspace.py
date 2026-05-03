from __future__ import annotations

import hashlib
import json
import shutil
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _safe_name(name: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in name)


@dataclass(slots=True)
class ProjectPaths:
    root: Path
    original_apk: Path
    baseline_dir: Path
    current_dir: Path
    outputs_dir: Path
    state_dir: Path
    keystore_dir: Path
    native_dir: Path
    native_projects_dir: Path
    metadata_file: Path


class WorkspaceManager:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()
        self.projects_dir = self.root / "projects"
        self.current_file = self.root / "current_project.json"
        self.projects_dir.mkdir(parents=True, exist_ok=True)

    def import_apk(self, apk_path: str | Path) -> dict[str, Any]:
        src = Path(apk_path).resolve()
        if not src.is_file():
            raise FileNotFoundError(f"APK 不存在: {src}")
        sha256 = _sha256_file(src)
        project_name = f"{src.stem}-{sha256[:12]}"
        project_root = self.projects_dir / _safe_name(project_name)
        paths = self._paths(project_root)
        for directory in [
            paths.root,
            paths.original_apk.parent,
            paths.outputs_dir,
            paths.state_dir,
            paths.keystore_dir,
            paths.native_dir,
            paths.native_projects_dir,
        ]:
            directory.mkdir(parents=True, exist_ok=True)
        if not paths.original_apk.exists() or _sha256_file(paths.original_apk) != sha256:
            shutil.copy2(src, paths.original_apk)

        metadata = {
            "project_id": project_root.name,
            "apk_name": src.name,
            "apk_sha256": sha256,
            "imported_at": _now(),
            "original_source_path": str(src),
            "workspace_apk_path": str(paths.original_apk),
            "baseline_dir": str(paths.baseline_dir),
            "current_dir": str(paths.current_dir),
            "outputs_dir": str(paths.outputs_dir),
            "native_dir": str(paths.native_dir),
            "native_projects_dir": str(paths.native_projects_dir),
        }
        self._write_json(paths.metadata_file, metadata)
        self.set_current_project(project_root.name)
        return metadata

    def list_projects(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for metadata_file in sorted(self.projects_dir.glob("*/metadata.json")):
            try:
                items.append(json.loads(metadata_file.read_text(encoding="utf-8")))
            except Exception:
                continue
        return items

    def set_current_project(self, project_id: str) -> dict[str, Any]:
        metadata = self.get_project(project_id)
        self._write_json(self.current_file, {"project_id": project_id, "selected_at": _now()})
        return metadata

    def get_current_project(self) -> dict[str, Any]:
        if not self.current_file.exists():
            raise FileNotFoundError("当前没有活动工作区项目")
        data = json.loads(self.current_file.read_text(encoding="utf-8"))
        return self.get_project(data["project_id"])

    def get_project(self, project_id: str) -> dict[str, Any]:
        metadata_file = self.projects_dir / project_id / "metadata.json"
        if not metadata_file.is_file():
            raise FileNotFoundError(f"项目不存在: {project_id}")
        return json.loads(metadata_file.read_text(encoding="utf-8"))

    def get_project_paths(self, project_id: str | None = None) -> ProjectPaths:
        if project_id is None:
            project_id = self.get_current_project()["project_id"]
        project_root = self.projects_dir / project_id
        if not project_root.is_dir():
            raise FileNotFoundError(f"项目不存在: {project_id}")
        return self._paths(project_root)

    def ensure_decoded_tree(self, project_id: str | None = None) -> ProjectPaths:
        paths = self.get_project_paths(project_id)
        paths.baseline_dir.mkdir(parents=True, exist_ok=True)
        paths.current_dir.mkdir(parents=True, exist_ok=True)
        return paths

    def resolve_current_path(self, rel_path: str, project_id: str | None = None) -> Path:
        return self._resolve_under(self.get_project_paths(project_id).current_dir, rel_path)

    def resolve_baseline_path(self, rel_path: str, project_id: str | None = None) -> Path:
        return self._resolve_under(self.get_project_paths(project_id).baseline_dir, rel_path)

    def make_output_path(self, filename: str, project_id: str | None = None) -> Path:
        paths = self.get_project_paths(project_id)
        safe_name = _safe_name(filename)
        out = (paths.outputs_dir / safe_name).resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        return out

    def reset_current_from_baseline(self, project_id: str | None = None) -> dict[str, Any]:
        paths = self.get_project_paths(project_id)
        if not paths.baseline_dir.exists():
            raise FileNotFoundError("baseline 解包目录不存在，请先 decode")
        if paths.current_dir.exists():
            shutil.rmtree(paths.current_dir)
        shutil.copytree(paths.baseline_dir, paths.current_dir)
        return {
            "ok": True,
            "project_id": paths.root.name,
            "current_dir": str(paths.current_dir),
            "baseline_dir": str(paths.baseline_dir),
        }

    def list_native_libraries(self, project_id: str | None = None, *, from_baseline: bool = False) -> dict[str, Any]:
        paths = self.get_project_paths(project_id)
        base = paths.baseline_dir if from_baseline else paths.current_dir
        libraries: list[dict[str, Any]] = []

        if base.exists():
            for path in sorted(base.rglob('*.so')):
                rel = path.relative_to(base).as_posix()
                if not rel.startswith('lib/'):
                    continue
                libraries.append(self._native_info(rel, source='decoded', full_path=path))

        if not libraries:
            with zipfile.ZipFile(paths.original_apk) as zf:
                for name in sorted(zf.namelist()):
                    if name.startswith('lib/') and name.endswith('.so'):
                        libraries.append(self._native_info(name, source='apk-zip', full_path=None))

        return {
            'ok': True,
            'project_id': paths.root.name,
            'from_baseline': from_baseline,
            'libraries': libraries,
            'total': len(libraries),
        }

    def materialize_native_library(self, relative_path: str, project_id: str | None = None, *, from_baseline: bool = False) -> Path:
        paths = self.get_project_paths(project_id)
        base = paths.baseline_dir if from_baseline else paths.current_dir
        if base.exists():
            candidate = self._resolve_under(base, relative_path)
            if candidate.is_file():
                return candidate

        with zipfile.ZipFile(paths.original_apk) as zf:
            if relative_path not in zf.namelist():
                raise FileNotFoundError(f'Native 库不存在: {relative_path}')
            out_path = self._resolve_under(paths.native_dir, relative_path)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(relative_path) as src, out_path.open('wb') as dst:
                shutil.copyfileobj(src, dst)
            return out_path

    def get_native_analysis_dir(self, relative_path: str, project_id: str | None = None) -> Path:
        paths = self.get_project_paths(project_id)
        parts = [p for p in Path(relative_path).with_suffix('').parts if p not in {'/', ''}]
        root = paths.native_projects_dir
        for part in parts:
            root = root / _safe_name(part)
        root.mkdir(parents=True, exist_ok=True)
        return root

    def _native_info(self, relative_path: str, *, source: str, full_path: Path | None) -> dict[str, Any]:
        parts = Path(relative_path).parts
        abi = parts[1] if len(parts) >= 3 else ''
        item = {
            'relative_path': relative_path,
            'abi': abi,
            'name': Path(relative_path).name,
            'source': source,
        }
        if full_path is not None:
            item['path'] = str(full_path)
            item['size'] = full_path.stat().st_size
        return item

    def _paths(self, project_root: Path) -> ProjectPaths:
        return ProjectPaths(
            root=project_root,
            original_apk=project_root / 'original' / 'app.apk',
            baseline_dir=project_root / 'decoded' / 'baseline',
            current_dir=project_root / 'decoded' / 'current',
            outputs_dir=project_root / 'outputs',
            state_dir=project_root / 'state',
            keystore_dir=project_root / 'keystore',
            native_dir=project_root / 'native',
            native_projects_dir=project_root / 'native-projects',
            metadata_file=project_root / 'metadata.json',
        )

    def _resolve_under(self, base: Path, rel_path: str) -> Path:
        target = (base / rel_path).resolve()
        if target != base and base not in target.parents:
            raise ValueError(f'非法路径，超出工作区: {rel_path}')
        return target

    def _write_json(self, path: Path, data: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
