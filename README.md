# Android Reverse MCP

一个面向 **无 GUI / Docker / Agent 自动化分析** 的 Android 逆向 MCP 入口。

当前集成：

- `jadx semantic`：DEX/Java/Kotlin 静态分析、xref、rename、源码读取
- `apktool`：解包、Smali/资源改写、重打包
- `sign-tools`：zipalign、签名、校验
- `diff`：工作区差异对比
- `ghidra-headless-mcp`：`.so` / native 静态分析

## 特点

- **单入口 MCP**
- **单容器**：不再依赖 IDA sidecar
- **工作区持久化**
- **固定 apktool 版本**
- **Docker 内自动安装 Ghidra**
- **Python 环境隔离**：统一走 `uv`

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
  ghidra/
  state/project-state.json
```

## 快速开始

### 1. 准备 `.env`

```bash
cp .env.example .env
```

示例：

```env
APK_PATH=/absolute/path/to/target.apk
WORKSPACE_DIR=/absolute/path/to/android-reverse-workspace
PORT=8651
DECODE_ON_START=1

GHIDRA_AUTO_START=1
GHIDRA_HEADLESS_MCP_FAKE_BACKEND=0
GHIDRA_BACKEND_HOST=127.0.0.1
GHIDRA_BACKEND_PORT=8765
```

### 2. 一键启动

```bash
docker compose up -d --build
```

主 MCP：

```text
http://127.0.0.1:8651/mcp
```

## 最短一键运行

直接用仓库里的脚本：

```bash
./scripts/run-docker.sh /absolute/path/to/app.apk
```

可选参数：

```bash
./scripts/run-docker.sh /absolute/path/to/app.apk /absolute/path/to/workspace 8651
```

脚本行为：

- 本地没有镜像时自动 `docker build`
- 自动挂载 APK 到 `/input/app.apk`
- 自动设置 `-e APK=/input/app.apk`
- 自动创建持久化工作区

## 单命令运行

```bash
docker run --rm -it \
  -p 8651:8651 \
  -v /path/to/workspace:/workspace \
  -v /path/to/app.apk:/input/app.apk:ro \
  -e APK=/input/app.apk \
  -e DECODE_ON_START=1 \
  android-reverse-mcp
```

## Ghidra backend 说明

本项目已改为使用 [`mrphrazer/ghidra-headless-mcp`](https://github.com/mrphrazer/ghidra-headless-mcp)。

容器启动时会：

1. 自动启动 `jadx` backend
2. 自动启动 `ghidra-headless-mcp` TCP backend
3. 主 MCP 自动桥接到 Ghidra backend

也就是说：

- 不需要手工开 GUI
- 不需要手工启动第二个 MCP
- `.so` 分析直接走统一入口

### Docker 内安装内容

当前镜像会自动下载并安装：

- **Ghidra 12.0.4**  
  来源：官方 GitHub release  
  https://github.com/NationalSecurityAgency/ghidra/releases
- **ghidra-headless-mcp**  
  来源：  
  https://github.com/mrphrazer/ghidra-headless-mcp

## 可用 Native / Ghidra Tools

- `ghidra_list_remote_tools`
- `ghidra_health`
- `ghidra_list_sessions`
- `ghidra_program_summary`
- `ghidra_save_program`
- `list_native_libraries`
- `open_native_library`
- `ghidra_list_functions`
- `ghidra_decompile_function`
- `ghidra_function_report`
- `ghidra_xrefs_to`
- `ghidra_xrefs_from`
- `ghidra_rename_function`
- `ghidra_list_variables`
- `ghidra_rename_variable`
- `ghidra_set_comment`

## 推荐工作流

### APK / DEX

1. `prepare_single_apk_workspace`
2. `get_android_manifest`
3. `get_main_activity_class`
4. `search_method_by_name`
5. `get_xrefs_to_method`
6. `get_class_source`

### Native / so

1. `list_native_libraries`
2. `open_native_library`
3. 从返回值里拿 `session_id`
4. `ghidra_list_functions`
5. `ghidra_decompile_function`
6. `ghidra_xrefs_to`
7. `ghidra_rename_function`
8. `ghidra_rename_variable`
9. `ghidra_save_program`

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

### Sign / Diff

- `sign_generate_debug_keystore`
- `sign_zipalign_apk`
- `sign_apk`
- `sign_verify_apk_signature`
- `diff_workspace_changes`
- `diff_decoded_file`

## 开发/本地测试

如果你要在宿主机直接跑 Ghidra MCP 做调试：

```bash
uv venv /home/root1/tools/ghidra-headless-mcp-venv
source /home/root1/tools/ghidra-headless-mcp-venv/bin/activate
uv pip install "https://github.com/mrphrazer/ghidra-headless-mcp/archive/b9c491a6383dbc68c581e7fed16341ac47e7faba.zip"
export GHIDRA_INSTALL_DIR=/path/to/ghidra
ghidra-headless-mcp --transport tcp --host 127.0.0.1 --port 8765
```

## GitHub 仓库元数据

仓库内已提供：

- `.github/repository-metadata.json`
- `scripts/apply_github_metadata.py`
- `scripts/apply_github_metadata.sh`
