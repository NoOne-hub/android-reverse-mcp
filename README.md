# Android Reverse MCP

一个面向 **无 GUI / Docker / Agent 自动化分析** 的 Android 逆向 MCP 入口。

当前集成：

- `jadx semantic`：DEX/Java/Kotlin 静态分析、xref、rename、源码读取
- `apktool`：解包、Smali/资源改写、重打包
- `sign-tools`：zipalign、签名、校验
- `diff`：工作区差异对比
- 可选 native backend sidecar：Ghidra 或 IDA 的 `.so` / native 静态分析

## 特点

- **单入口 MCP**
- **共享 `native_*` 工具面**：native 分析入口对后端无感
- **sidecar 可选**：可接 Ghidra 或 IDA native backend
- **工作区持久化**
- **固定 apktool 版本**
- **Python 环境隔离**：统一走 `uv`

## 文档

- `docs/single-apk-agent-workflow.md`：给大模型 / Agent 的单 APK 标准分析工作流与提示词模板

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
  native-projects/
  state/project-state.json
```

## 快速开始

### 0. 准备本地构建产物

Docker 构建不会在镜像内下载大体积 Ghidra 资源，构建前需要先把以下文件放到仓库本地：

- `third_party/ghidra_12.0.4_PUBLIC_20260303.zip`
- `third_party/ghidra-headless-mcp-b9c491a6383dbc68c581e7fed16341ac47e7faba.zip`
- `java-backend/target/headless-jadx-backend-0.1.0.jar`

如果本地还没有 Java backend JAR，可先执行：

```bash
mvn -f java-backend/pom.xml package
```

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

NATIVE_BACKEND=ghidra
NATIVE_BACKEND_URL=tcp://ghidra-sidecar:8765
GHIDRA_BACKEND=tcp://ghidra-sidecar:8765

# IDA sidecar still uses HTTP MCP:
# NATIVE_BACKEND=ida
# NATIVE_BACKEND_URL=http://ida-sidecar:8745/mcp
```

### 2. 一键启动

完整 Ghidra 栈：

```bash
docker compose --profile full-ghidra up -d --build
```

完整 IDA 栈：

```bash
docker compose --profile full-ida up -d --build
```

仅 sidecar：

```bash
docker compose --profile ghidra-only up -d ghidra-sidecar
docker compose --profile ida-only up -d ida-sidecar
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
./scripts/run-docker.sh /absolute/path/to/app.apk /absolute/path/to/workspace 8651 ghidra
./scripts/run-docker.sh /absolute/path/to/app.apk /absolute/path/to/workspace 8651 ida
```

脚本行为：

- 自动选择 `full-ghidra` 或 `full-ida` profile
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

## Native backend 说明

主 MCP 通过共享 `native_*` 工具面对接选定的 native backend。

当前架构目标：

1. 主 MCP 始终暴露统一的 `native_*` 工具
2. Ghidra 和 IDA 以 sidecar 形式独立运行
3. 通过 `NATIVE_BACKEND` / `NATIVE_BACKEND_URL` 在启动时选择后端

也就是说：

- `.so` 分析始终走统一入口
- backend-specific 能力未来放在 `native_ghidra_*` 或 `native_ida_*`
- main MCP 与 native sidecar 可分离启动

### 当前 native sidecar 形态

- **Ghidra**：`ghidra-headless-mcp` TCP sidecar
- **IDA**：`root1/idapro:9.3-cli-mcp`，以 `idalib-mcp` 方式运行

### Native 共享工具

- `native_health`
- `native_list_remote_tools`
- `native_list_sessions`
- `list_native_libraries`
- `open_native_library`
- `native_program_summary`
- `native_save_program`
- `native_list_functions`
- `native_decompile_function`
- `native_function_report`
- `native_xrefs_to`
- `native_xrefs_from`
- `native_rename_function`
- `native_list_variables`
- `native_rename_variable`
- `native_set_comment`

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
4. `native_list_functions`
5. `native_decompile_function`
6. `native_xrefs_to`
7. `native_rename_function`
8. `native_rename_variable`
9. `native_save_program`

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
