# 单 APK 自动化分析工作流（给大模型 / Agent 用）

这份文档用于指导大模型通过 **`android-reverse-mcp` 单一入口** 自动分析一个 APK。

适用场景：

- 分析 Java / Kotlin / DEX 逻辑
- 分析 APK 内的 `lib/*.so`
- 做重命名、注释、回溯引用
- 后续需要 Smali 修改、重打包、签名

---

## 核心原则

1. **只连接一个 MCP**
   - 入口始终是 `android-reverse-mcp`
   - 不要额外手工连接 `jadx` 或 `ghidra`
2. **先 Java / Manifest，再 native**
   - 先理解入口、组件、可疑类、关键方法
   - 再看 `so` 是否参与关键流程
3. **先缩小范围，再深挖**
   - 先找主入口、认证、加密、网络、JNI 相关调用
   - 再决定具体下钻哪个类 / 方法 / 函数
4. **native 分析必须先打开 session**
   - 先 `list_native_libraries`
   - 再 `open_native_library`
   - 后续所有 `native_*` 都带 `session_id`

---

## 标准分析顺序

### 阶段 1：确认环境与目标

先调用：

- `health`
- `workspace_get_current_project`

目标：

- 确认当前 APK 已加载
- 确认 `native_enabled=true`
- 记录当前项目 ID

---

### 阶段 2：获取 APK 入口信息

优先调用：

- `get_android_manifest`
- `get_main_activity_class`
- `get_package_tree`

如果需要，再调用：

- `get_manifest_component`
- `get_all_resource_file_names`
- `get_resource_file`

目标：

- 找到包名、主 Activity、Service、Receiver、Provider
- 判断壳、热修复、插件化、动态加载迹象
- 判断是否存在明显的 native / JNI 入口

重点关注：

- `android:name`
- `android:process`
- `exported`
- `intent-filter`
- `uses-permission`
- `meta-data`

---

### 阶段 3：Java / Kotlin 层初筛

优先调用：

- `search_method_by_name`
- `search_classes_by_keyword`
- `get_class_source`
- `get_methods_of_class`
- `get_strings`

建议优先搜索这些关键词：

- `native`
- `loadLibrary`
- `System.load`
- `System.loadLibrary`
- `JNI`
- `encrypt`
- `decrypt`
- `sign`
- `verify`
- `token`
- `login`
- `check`
- `root`
- `debug`
- `ssl`
- `pinning`
- `http`
- `request`
- `retrofit`
- `okhttp`
- `webview`

目标：

- 找到关键业务入口
- 找到 JNI 桥接点
- 找到加密、校验、签名、风控、反调试、证书校验逻辑

---

### 阶段 4：引用回溯

对关键类 / 方法继续调用：

- `get_xrefs_to_class`
- `get_xrefs_to_method`
- `get_xrefs_to_field`

目标：

- 看关键逻辑是谁触发的
- 看调用链是在 UI、网络层、鉴权层还是 JNI 层

如果一个方法名不清晰，可以结合：

- `rename_class`
- `rename_method`
- `rename_field`
- `rename_variable`

把语义整理清楚。

---

### 阶段 5：判断是否进入 native

如果 Java 层出现以下迹象，就继续 native：

- `System.loadLibrary(...)`
- 存在 `native` 方法声明
- 校验 / 解密 / 风控核心逻辑只做了薄包装
- 字符串、密钥、算法入口明显转发到 JNI

然后调用：

- `list_native_libraries`

目标：

- 列出 APK 内所有 `.so`
- 判断 ABI 分布
- 锁定疑似目标库

---

### 阶段 6：打开并分析 so

先调用：

- `open_native_library`

示例参数：

```json
{
  "relative_path": "lib/arm64-v8a/libfoo.so"
}
```

它会返回：

- `session_id`

后续所有 native 分析都基于这个 `session_id`。

---

### 阶段 7：native 初筛

优先调用：

- `native_list_functions`
- `native_decompile_function`
- `native_function_report`

建议优先关注：

- 导出函数
- `JNI_OnLoad`
- `Java_*`
- 带有 `check` / `verify` / `sign` / `encrypt` / `decrypt` / `token` / `auth` / `ssl` / `pin` / `root` / `debug` 语义的函数
- 被 Java 层 JNI 方法名映射到的函数

目标：

- 建立 Java ↔ JNI ↔ native 核心逻辑映射
- 判断真实关键逻辑是不是在 so 里

---

### 阶段 8：native 交叉引用与整理

继续调用：

- `native_xrefs_to`
- `native_xrefs_from`
- `native_list_variables`
- `native_rename_function`
- `native_rename_variable`
- `native_set_comment`

目标：

- 理清函数之间的调用关系
- 给无意义函数名补语义
- 给局部变量、参数、关键地址补注释

完成后可调用：

- `native_save_program`

保存分析状态。

---

### 阶段 9：需要改包时再进入重打包流程

如果分析目标包含 Smali / 资源修改、重签名、验证，则继续：

- `apktool_decode_current`
- `apktool_read_file`
- `apktool_write_file`
- `apktool_build_current`
- `sign_generate_debug_keystore`
- `sign_zipalign_apk`
- `sign_apk`
- `sign_verify_apk_signature`
- `rebuild_and_sign_current_apk`

如果只是静态分析，不必提前进入这一步。

---

## 给大模型的建议决策逻辑

### 什么时候优先看 Java

满足任一条件时优先 Java：

- 需要先定位业务入口
- 需要看 Activity / Service / Receiver
- 需要看网络调用、路由、权限、WebView、反调试开关
- 需要判断 JNI 是在哪个时机触发的

### 什么时候切到 native

满足任一条件时切 native：

- Java 只有薄封装，关键逻辑是 `native`
- `System.loadLibrary` 明确存在
- Java 层只是把参数传入 JNI
- 可疑字符串或算法线索停在 `so`

### 什么时候做 rename

满足任一条件时应立即 rename：

- 方法 / 变量名无语义，影响后续分析
- 调用链已经基本明确
- 需要给下一个大模型轮次保留上下文

---

## 推荐输出格式

每轮分析尽量按这个结构输出：

1. **当前结论**
2. **关键证据**
3. **下一步目标**

例如：

- 当前结论：登录 token 生成入口在 `com.xxx.auth.TokenManager.signRequest`
- 关键证据：该方法调用了 `nativeSign`，并加载 `libsec.so`
- 下一步目标：打开 `libsec.so`，定位 `nativeSign` 对应 JNI 函数并反编译

---

## 可直接给大模型使用的提示词模板

你正在使用 `android-reverse-mcp` 分析一个 Android APK。  
要求：

1. 只使用当前 MCP 提供的工具，不要假设有 GUI。
2. 先分析 Manifest、主 Activity、包结构，再分析关键类和方法。
3. 主动搜索 JNI / `System.loadLibrary` / `native` 方法。
4. 如果 APK 内存在 `.so`，先 `list_native_libraries`，再 `open_native_library`，之后使用 `native_*` 工具分析。
5. 发现关键方法、关键函数后，必要时使用 rename 和 comment 工具整理语义。
6. 每一轮输出：
   - 当前发现
   - 证据
   - 下一步要调用的工具
7. 优先关注：
   - 登录 / 鉴权 / token / 签名
   - 加解密
   - SSL pinning / 证书校验
   - root / debug / anti-tamper
   - JNI 桥接的核心逻辑

请从 `health`、`get_android_manifest`、`get_main_activity_class` 开始。

---

## 最小工具序列示例

### 纯 Java 入口

1. `health`
2. `get_android_manifest`
3. `get_main_activity_class`
4. `search_method_by_name`
5. `get_class_source`
6. `get_xrefs_to_method`

### Java + native

1. `health`
2. `get_android_manifest`
3. `search_method_by_name`（`loadLibrary` / `native`）
4. `list_native_libraries`
5. `open_native_library`
6. `native_list_functions`
7. `native_decompile_function`
8. `native_xrefs_to`
9. `native_save_program`

