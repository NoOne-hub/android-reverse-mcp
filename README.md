# Android Reverse MCP

一个面向 **无 GUI / Docker / Agent 自动化分析** 的 Android 逆向 MCP 入口。

当前已集成：

- `jadx semantic`：类/方法/字段、源码、manifest、resources、xref、rename
- `apktool`：解包、Smali/资源读写、重建
- `sign-tools`：keystore、zipalign、签名、校验
- `diff`：baseline/current 差异对比
- `ida sidecar`：预留接入位

## 特点

- **单入口 MCP**
- **单 Docker** 完成单 APK 分析链路
- **工作区持久化**，支持二次进入与 rename 状态恢复
- **固定 apktool 版本**：仓库内置官方 `apktool_3.0.2.jar`

## 工作区结构

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

## Docker

构建：

```bash
docker build -t android-reverse-mcp .
```

一键启动单 APK：

```bash
docker run --rm -it   -p 8651:8651   -v /path/to/workspace:/workspace   -v /path/to/app.apk:/input/app.apk:ro   -e APK=/input/app.apk   -e DECODE_ON_START=1   android-reverse-mcp
```

如果要覆盖端口：

```bash
docker run --rm -it   -p 9000:9000   -v /path/to/workspace:/workspace   -v /path/to/app.apk:/input/app.apk:ro   -e APK=/input/app.apk   -e PORT=9000   -e DECODE_ON_START=1   android-reverse-mcp
```

MCP 地址：

```text
http://127.0.0.1:8651/mcp
```

也可以继续手工传完整参数：

```bash
docker run --rm -it android-reverse-mcp --help
```

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

## GitHub 仓库元数据

仓库内已提供：

- `.github/repository-metadata.json`
- `scripts/apply_github_metadata.sh`

有 `GITHUB_TOKEN` 时可直接应用：

```bash
GITHUB_TOKEN=xxx ./scripts/apply_github_metadata.sh
```

## 路线图

- headless IDA sidecar
- 多 APK 差异工作流
- 更高层自动分析 orchestrator

## License

Apache License 2.0
