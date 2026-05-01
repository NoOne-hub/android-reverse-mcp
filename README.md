# Android Reverse MCP

一个面向 **无 GUI / Docker / 大模型自动化分析** 的 Android 逆向 MCP 网关。

它不是单纯的 `jadx-mcp`，而是一个统一入口，当前已经集成：

- `jadx semantic`：DEX/Java/Kotlin 语义分析、xref、rename
- `apktool`：APK 解包、Smali/资源读写、重建
- `sign-tools`：debug keystore、zipalign、签名、校验
- `diff`：baseline/current 工作区差异比对
- `ida sidecar`：**预留接入位**，后续可挂 headless IDA MCP 分析 `.so`

## 设计目标

- **一个 MCP 入口**，而不是多个分散服务
- **一个主 Docker** 跑完单 APK 分析链路
- **工作区持久化**，方便二次进入、恢复 rename 状态、持续 patch
- **适合 Agent / LLM**：结构化、按需调用、减少 token 浪费

## 当前架构

```text
MCP Client
   ↓
Python FastMCP Gateway
   ├── HTTP -> Java Headless Backend (jadx-core)
   ├── apktool wrapper
   ├── sign-tools wrapper
   ├── diff wrapper
   └── ida bridge (reserved)
```

## 已实现能力

### JADX / 语义分析

- `load_apk`
- `get_all_classes`
- `get_class_source`
- `get_methods_of_class`
- `get_fields_of_class`
- `get_method_by_name`
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

### Rename / 状态恢复

- `rename_class`
- `rename_method`
- `rename_field`
- `rename_package`
- `rename_variable`
- `list_renames`
- `get_method_variables`
- `export_project_state`
- `import_project_state`

### Workspace

- `workspace_import_apk`
- `workspace_list_projects`
- `workspace_select_project`
- `workspace_get_current_project`
- `prepare_single_apk_workspace`
- `list_output_files`

### APKTool

- `apktool_decode_current`
- `apktool_reset_current`
- `apktool_list_current_files`
- `apktool_read_file`
- `apktool_write_file`
- `apktool_build_current`
- `load_rebuilt_apk_to_jadx`

### Sign Tools

- `sign_generate_debug_keystore`
- `sign_zipalign_apk`
- `sign_apk`
- `sign_verify_apk_signature`
- `rebuild_and_sign_current_apk`

### Diff

- `diff_workspace_changes`
- `diff_decoded_file`

## 工作区模型

每个 APK 会被导入到统一 workspace：

```text
/workspace/projects/<project_id>/
  original/app.apk
  decoded/
    baseline/
    current/
  outputs/
  keystore/
  state/project-state.json
```

其中：

- `baseline`：初始解包结果
- `current`：当前可修改工作副本
- `outputs`：重建/签名产物
- `state`：rename 等分析状态

## Rename 行为说明

当前 rename 是 **JADX 语义 alias 层**，不是直接写回 dex：

- 会影响反编译源码显示
- 适合大模型给类/方法/字段/变量做语义命名
- 不直接改 APK
- 成功后会自动尝试写入：
  - `/workspace/projects/<project_id>/state/project-state.json`

重新执行：

- `prepare_single_apk_workspace`
- `load_rebuilt_apk_to_jadx`

时，会尝试自动恢复已保存的 rename 状态。

## 本地开发

建议用 `uv`，不要污染系统 Python：

```bash
uv venv .venv
source .venv/bin/activate
uv pip install -e .
```

### 启动 MCP

```bash
android_reverse_mcp --http --host 127.0.0.1 --port 8651 --apk ./samples/TestActivity.apk
```

兼容旧名字：

```bash
headless_jadx_mcp --http --host 127.0.0.1 --port 8651 --apk ./samples/TestActivity.apk
```

## Docker

### 构建

```bash
docker build -t android-reverse-mcp .
```

### 运行

```bash
docker run --rm -it \
  -p 8651:8651 \
  -v /path/to/workspace:/workspace \
  -v /path/to/app.apk:/input/app.apk:ro \
  android-reverse-mcp \
  --http --host 0.0.0.0 --port 8651 --apk /input/app.apk --decode-on-start
```

MCP 地址：

```text
http://127.0.0.1:8651/mcp
```

## 推荐单 APK 工作流

### 1. 一键准备工作区

- `prepare_single_apk_workspace`

它会：

1. 导入 APK
2. 生成 workspace project
3. 可选 decode 到 `baseline/current`
4. 把原始 APK 加载到 JADX backend

### 2. 语义分析

- `get_main_activity_class`
- `get_android_manifest`
- `search_method_by_name`
- `get_xrefs_to_method`
- `get_class_source`

### 3. 补 rename

- `get_methods_of_class`
- `get_method_variables`
- `rename_*`
- `list_renames`

### 4. Patch / 重建 / 签名

- `apktool_read_file`
- `apktool_write_file`
- `diff_workspace_changes`
- `rebuild_and_sign_current_apk`
- `load_rebuilt_apk_to_jadx`

## 当前边界

还没接入的重点：

- headless IDA sidecar
- 多 APK 差异分析工作流
- 持久化 comments / notes / findings
- 更高层的自动分析 orchestrator

## License

本项目采用 **Apache License 2.0**，见 `LICENSE`。
