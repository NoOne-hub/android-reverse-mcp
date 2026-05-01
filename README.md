# Android Reverse MCP

一个面向 **无 GUI / Docker / Agent 自动化分析** 的 Android 逆向 MCP 入口。

当前已集成：

- `jadx semantic`：类/方法/字段、源码、manifest、resources、xref、rename
- `apktool`：解包、Smali/资源读写、重建
- `sign-tools`：keystore、zipalign、签名、校验
- `diff`：baseline/current 差异对比
- `ida sidecar`：通过 `idalib-mcp` 无头分析 `.so`

## 特点

- **单入口 MCP**
- **双容器 compose**：主服务 + IDA sidecar
- **工作区持久化**，支持二次进入与 rename 状态恢复
- **固定 apktool 版本**：仓库内置官方 `apktool_3.0.2.jar`
- **Python 环境隔离**：主服务 / sidecar / 宿主机测试都可走 `uv`
- **IDA sidecar 不需要手工开 GUI**，后续可直接 `docker compose up -d`

## 工作区结构

```text
/workspace/projects/<project_id>/
  original/app.apk
  decoded/
    baseline/
    current/
  outputs/
  keystore/
  native/
  ida/
  state/project-state.json
```

## 快速开始

### 1. 准备 `.env`

复制一份：

```bash
cp .env.example .env
```

编辑 `.env`：

```env
APK_PATH=/absolute/path/to/target.apk
WORKSPACE_DIR=/absolute/path/to/android-reverse-workspace
PORT=8651

IDA_DIR=/absolute/path/to/ida-pro
IDA_USER_DIR=/absolute/path/to/.idapro
IDA_MCP_PORT=8745
IDA_MCP_ISOLATED_CONTEXTS=0
IDA_MCP_UNSAFE=0
```

### 2. 一键启动

```bash
docker compose up -d --build
```

主 MCP：

```text
http://127.0.0.1:8651/mcp
```

IDA sidecar：

```text
http://127.0.0.1:8745/mcp
```

### 3. 单容器临时跑法

如果你暂时不想走 compose，也可以继续单独跑主服务：

```bash
docker run --rm -it \
  -p 8651:8651 \
  -v /path/to/workspace:/workspace \
  -v /path/to/app.apk:/input/app.apk:ro \
  -e APK=/input/app.apk \
  -e DECODE_ON_START=1 \
  android-reverse-mcp
```

## IDA sidecar 说明

本项目使用 [`mrexodia/ida-pro-mcp`](https://github.com/mrexodia/ida-pro-mcp) 的 **`idalib-mcp`** 模式，而不是 GUI 插件模式。

也就是说：

- 不要求你手工打开 IDA GUI
- 不要求你手工启动 MCP
- `docker compose up -d` 后，主服务自动连 sidecar
- 分析 `.so` 时通过 `idalib_open()` 动态加载

### sidecar 用到什么

- 宿主机已安装好的 IDA 目录：`IDA_DIR`
- 宿主机 IDA 用户目录：`IDA_USER_DIR`
- 容器内会自动安装 `ida-pro-mcp`
- sidecar 启动时自动设置：
  - `IDADIR=/opt/ida-pro`
  - `IDAUSR=/root/.idapro`
  - `LD_LIBRARY_PATH=/opt/ida-pro`

### 当前已知前提

要让 `idalib_open()` 真正打开二进制，**IDA 必须已经完成 batch/headless 许可接受**。

如果 sidecar 日志里出现：

```text
License not yet accepted, cannot run in batch mode
```

说明不是 bridge 问题，而是 **IDA 还没完成首次接受流程**。

### 关于 WSL2

WSL2 下 IDA GUI 可能不稳定，甚至出现：

- 缺 OpenGL / Qt 运行库
- `malloc(): unaligned tcache chunk detected`
- GUI 无法正常启动

这不一定影响 `idat` / `idalib-mcp` 的无头使用，但**首次许可接受**通常更容易在一个正常 GUI Linux 环境里完成。

如果 WSL2 GUI 不稳定，建议：

1. 在可正常显示 GUI 的 Linux 环境里先把 IDA 打开一次
2. 走完 license / accept 流程
3. 再把对应 `IDA_USER_DIR` 带回来用于 headless sidecar

## IDA Python 绑定（可选）

如果你还想在宿主机本地直接用 IDA / IDAPython，而不是只跑 sidecar，可以把 IDA 的 Python 绑到一个独立 `uv` 管理版本，不再使用系统 Python。

### 安装独立 Python

```bash
uv python install 3.12.13
```

### 切给 IDA

```bash
/home/root1/tools/ida-pro/idapyswitch \
  --force-path ~/.local/share/uv/python/cpython-3.12.13-linux-x86_64-gnu/lib/libpython3.12.so.1.0
```

说明：

- 这是 **宿主机本地 IDA** 的 Python 绑定
- **不是 sidecar 必需条件**
- sidecar 自己会在容器里装独立 Python 环境

## 主要 MCP Tools

### Workspace
- `prepare_single_apk_workspace`
- `workspace_import_apk`
- `workspace_list_projects`
- `workspace_select_project`
- `workspace_get_current_project`
- `export_project_state`
- `import_project_state`
- `list_output_files`

### JADX
- `load_apk`
- `get_all_classes`
- `get_class_source`
- `get_methods_of_class`
- `get_fields_of_class`
- `search_method_by_name`
- `search_classes_by_keyword`
- `get_smali_of_class`
- `get_android_manifest`
- `get_manifest_component`
- `get_strings`
- `get_all_resource_file_names`
- `get_resource_file`
- `get_main_activity_class`
- `get_package_tree`
- `get_xrefs_to_class`
- `get_xrefs_to_method`
- `get_xrefs_to_field`

### Rename
- `rename_class`
- `rename_method`
- `rename_field`
- `rename_package`
- `rename_variable`
- `get_method_variables`
- `list_renames`

### APKTool / Build
- `apktool_decode_current`
- `apktool_reset_current`
- `apktool_list_current_files`
- `apktool_read_file`
- `apktool_write_file`
- `apktool_build_current`
- `load_rebuilt_apk_to_jadx`
- `rebuild_and_sign_current_apk`

### Native / IDA
- `ida_list_remote_tools`
- `ida_health`
- `ida_list_sessions`
- `ida_current_session`
- `ida_save_session`
- `list_native_libraries`
- `open_native_library`
- `ida_list_functions`
- `ida_decompile_function`
- `ida_disasm_function`
- `ida_xrefs_to`
- `ida_rename_function`
- `ida_append_comment`

### Sign / Diff
- `sign_generate_debug_keystore`
- `sign_zipalign_apk`
- `sign_apk`
- `sign_verify_apk_signature`
- `diff_workspace_changes`
- `diff_decoded_file`

## 推荐单 APK + so 工作流

### 1. 准备工作区

- `prepare_single_apk_workspace`

### 2. APK / DEX 分析

- `get_main_activity_class`
- `get_android_manifest`
- `search_method_by_name`
- `get_xrefs_to_method`
- `get_class_source`

### 3. Native 库发现

- `list_native_libraries`

### 4. 打开 so 到 IDA sidecar

- `open_native_library`
- `ida_current_session`
- `ida_list_functions`
- `ida_decompile_function`
- `ida_xrefs_to`
- `ida_rename_function`
- `ida_append_comment`

## GitHub 仓库元数据

仓库内已提供：

- `.github/repository-metadata.json`
- `scripts/apply_github_metadata.py`
- `scripts/apply_github_metadata.sh`

有 `GITHUB_TOKEN` 时可直接应用：

```bash
GITHUB_TOKEN=xxx ./scripts/apply_github_metadata.sh
```

## 路线图

- 完整打通 `idalib_open()` / batch acceptance 后的联调
- 更多 native tools（imports/exports/strings/stack/type）
- 多 APK 差异工作流
- 更高层自动分析 orchestrator

## License

Apache License 2.0
