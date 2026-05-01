from __future__ import annotations

from pathlib import Path

from ..workspace import WorkspaceManager
from .commands import ensure_command, run_command


def generate_debug_keystore(
    workspace: WorkspaceManager,
    *,
    keystore_name: str = "debug.keystore",
    alias: str = "androiddebugkey",
    storepass: str = "android",
    keypass: str = "android",
    dname: str = "CN=Android Debug,O=Android,C=US",
    validity_days: int = 10000,
    project_id: str | None = None,
) -> dict:
    ensure_command("keytool")
    paths = workspace.get_project_paths(project_id)
    keystore_path = paths.keystore_dir / keystore_name
    if keystore_path.exists():
        return {
            "ok": True,
            "project_id": paths.root.name,
            "keystore_path": str(keystore_path),
            "alias": alias,
            "skipped": True,
        }
    cmd = [
        "keytool",
        "-genkeypair",
        "-v",
        "-keystore",
        str(keystore_path),
        "-storepass",
        storepass,
        "-alias",
        alias,
        "-keypass",
        keypass,
        "-keyalg",
        "RSA",
        "-keysize",
        "2048",
        "-validity",
        str(validity_days),
        "-dname",
        dname,
    ]
    result = run_command(cmd)
    result.update({"project_id": paths.root.name, "keystore_path": str(keystore_path), "alias": alias})
    return result


def zipalign_apk(
    workspace: WorkspaceManager,
    apk_path: str,
    *,
    output_name: str = "aligned.apk",
    project_id: str | None = None,
) -> dict:
    ensure_command("zipalign")
    out_path = workspace.make_output_path(output_name, project_id)
    cmd = ["zipalign", "-f", "4", apk_path, str(out_path)]
    result = run_command(cmd)
    result.update({"output_apk": str(out_path)})
    return result


def sign_apk(
    workspace: WorkspaceManager,
    apk_path: str,
    *,
    output_name: str = "signed.apk",
    keystore_path: str | None = None,
    alias: str = "androiddebugkey",
    storepass: str = "android",
    keypass: str = "android",
    project_id: str | None = None,
) -> dict:
    ensure_command("apksigner")
    paths = workspace.get_project_paths(project_id)
    effective_keystore = Path(keystore_path) if keystore_path else paths.keystore_dir / "debug.keystore"
    if not effective_keystore.is_file():
        raise FileNotFoundError(f"keystore 不存在: {effective_keystore}")
    out_path = workspace.make_output_path(output_name, project_id)
    cmd = [
        "apksigner",
        "sign",
        "--ks",
        str(effective_keystore),
        "--ks-key-alias",
        alias,
        "--ks-pass",
        f"pass:{storepass}",
        "--key-pass",
        f"pass:{keypass}",
        "--out",
        str(out_path),
        apk_path,
    ]
    result = run_command(cmd)
    result.update(
        {
            "project_id": paths.root.name,
            "keystore_path": str(effective_keystore),
            "output_apk": str(out_path),
            "alias": alias,
        }
    )
    return result


def verify_apk_signature(apk_path: str) -> dict:
    ensure_command("apksigner")
    cmd = ["apksigner", "verify", "--print-certs", "--verbose", apk_path]
    return run_command(cmd)
