package mcp.jadx;

import jadx.api.ICodeInfo;
import jadx.api.JadxArgs;
import jadx.api.JadxDecompiler;
import jadx.api.JavaClass;
import jadx.api.JavaField;
import jadx.api.JavaMethod;
import jadx.api.JavaNode;
import jadx.api.JavaPackage;
import jadx.api.JavaVariable;
import jadx.api.data.ICodeRename;
import jadx.api.data.impl.JadxCodeData;
import jadx.api.data.impl.JadxCodeRef;
import jadx.api.data.impl.JadxCodeRename;
import jadx.api.data.impl.JadxNodeRef;
import jadx.api.metadata.ICodeAnnotation;
import org.w3c.dom.Document;
import org.w3c.dom.Element;
import org.w3c.dom.NodeList;

import javax.xml.parsers.DocumentBuilderFactory;

import java.io.StringReader;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Base64;
import java.util.Collection;
import java.util.Collections;
import java.util.Comparator;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.stream.Collectors;

import org.xml.sax.InputSource;

public class AnalyzerService {
    private static final String ANDROID_NS = "http://schemas.android.com/apk/res/android";

    private final int threads;

    private JadxDecompiler decompiler;
    private Path currentApk;
    private String currentProjectId;
    private Instant loadedAt;
    private ManifestInfo manifestInfo;
    private final Map<String, JavaClass> classes = new LinkedHashMap<>();
    private Path tempDir;
    private Path resourcesDir;
    private final Map<String, Path> resourceEntries = new LinkedHashMap<>();
    private JadxCodeData codeData;

    public AnalyzerService(int threads) {
        this.threads = threads;
    }

    public synchronized Map<String, Object> health() {
        return Map.of(
                "ok", true,
                "loaded", decompiler != null,
                "project_id", currentProjectId,
                "apk_path", currentApk == null ? null : currentApk.toString(),
                "loaded_at", loadedAt == null ? null : loadedAt.toString(),
                "class_count", classes.size(),
                "resource_count", resourceEntries.size());
    }

    public synchronized Map<String, Object> loadApk(Path apkPath) throws Exception {
        close();

        Path outDir = Files.createTempDirectory("headless-jadx-");
        JadxArgs args = new JadxArgs();
        args.addInputFile(apkPath.toFile());
        args.setOutDir(outDir.toFile());
        args.setOutDirRes(outDir.resolve("resources").toFile());
        args.setSkipResources(false);
        args.setSkipSources(true);
        args.setShowInconsistentCode(true);
        args.setThreadsCount(threads);
        JadxCodeData renameData = new JadxCodeData();
        args.setCodeData(renameData);

        JadxDecompiler jadx = new JadxDecompiler(args);
        jadx.load();
        jadx.saveResources();

        Map<String, JavaClass> loadedClasses = new LinkedHashMap<>();
        for (JavaClass cls : jadx.getClassesWithInners()) {
            loadedClasses.put(cls.getFullName(), cls);
        }

        Map<String, Path> loadedResources = new LinkedHashMap<>();
        Path resDir = outDir.resolve("resources");
        if (Files.exists(resDir)) {
            try (var stream = Files.walk(resDir)) {
                stream.filter(Files::isRegularFile).forEach(path -> loadedResources.put(resDir.relativize(path).toString().replace('\\', '/'), path));
            }
        }
        String manifestXml = null;
        Path manifestPath = loadedResources.get("AndroidManifest.xml");
        if (manifestPath != null) {
            manifestXml = Files.readString(manifestPath);
        }

        this.decompiler = jadx;
        this.currentApk = apkPath.toAbsolutePath().normalize();
        this.loadedAt = Instant.now();
        this.currentProjectId = buildProjectId(apkPath);
        this.tempDir = outDir;
        this.resourcesDir = resDir;
        this.classes.clear();
        this.classes.putAll(loadedClasses);
        this.resourceEntries.clear();
        this.resourceEntries.putAll(loadedResources);
        this.manifestInfo = parseManifest(manifestXml);
        this.codeData = renameData;

        return currentProject();
    }

    public synchronized Map<String, Object> currentProject() {
        ensureLoaded();
        return Map.of(
                "ok", true,
                "project_id", currentProjectId,
                "apk_path", currentApk.toString(),
                "loaded_at", loadedAt.toString(),
                "class_count", classes.size(),
                "resource_count", resourceEntries.size(),
                "package_count", buildPackageTree().size(),
                "manifest_package", manifestInfo.packageName,
                "main_activity", manifestInfo.mainActivity);
    }

    public synchronized Map<String, Object> listProjects() {
        ensureLoaded();
        return Map.of(
                "ok", true,
                "projects", List.of(currentProject()),
                "active_project_id", currentProjectId);
    }

    public synchronized Map<String, Object> getAllClasses(int offset, int count) {
        ensureLoaded();
        return page("classes", new ArrayList<>(classes.keySet()), offset, count);
    }

    public synchronized Map<String, Object> getClassSource(String className) {
        JavaClass cls = requireClass(className);
        return Map.of(
                "ok", true,
                "class_name", className,
                "source", cls.getCode(),
                "line_count", countLines(cls.getCode()));
    }

    public synchronized Map<String, Object> getMethodsOfClass(String className) {
        JavaClass cls = requireClass(className);
        String code = cls.getCode();
        List<Map<String, Object>> methods = cls.getMethods().stream()
                .map(m -> methodSummary(cls, m, code))
                .collect(Collectors.toList());
        return Map.of("ok", true, "class_name", className, "methods", methods);
    }

    public synchronized Map<String, Object> getFieldsOfClass(String className) {
        JavaClass cls = requireClass(className);
        String code = cls.getCode();
        List<Map<String, Object>> fields = cls.getFields().stream()
                .map(f -> fieldSummary(cls, f, code))
                .collect(Collectors.toList());
        return Map.of("ok", true, "class_name", className, "fields", fields);
    }

    public synchronized Map<String, Object> getMethodByName(String className, String methodName) {
        JavaClass cls = requireClass(className);
        String code = cls.getCode();
        List<Map<String, Object>> matches = cls.getMethods().stream()
                .filter(m -> methodMatches(m, methodName))
                .map(m -> {
                    Map<String, Object> item = new LinkedHashMap<>(methodSummary(cls, m, code));
                    item.put("code", m.getCodeStr());
                    return item;
                })
                .collect(Collectors.toList());
        return Map.of("ok", true, "class_name", className, "method_name", methodName, "matches", matches, "total", matches.size());
    }

    public synchronized Map<String, Object> searchMethodByName(String methodName) {
        ensureLoaded();
        List<Map<String, Object>> matches = new ArrayList<>();
        for (JavaClass cls : classes.values()) {
            String code = cls.getCode();
            for (JavaMethod m : cls.getMethods()) {
                if (methodMatches(m, methodName)) {
                    matches.add(methodSummary(cls, m, code));
                }
            }
        }
        return Map.of("ok", true, "method_name", methodName, "matches", matches, "total", matches.size());
    }

    public synchronized Map<String, Object> searchClassesByKeyword(String searchTerm, String pkg, String searchIn, int offset, int count) {
        ensureLoaded();
        Set<String> scopes = parseScopes(searchIn);
        List<Map<String, Object>> matches = new ArrayList<>();
        String lower = searchTerm.toLowerCase(Locale.ROOT);

        for (JavaClass cls : classes.values()) {
            if (!pkg.isBlank() && !cls.getFullName().startsWith(pkg)) {
                continue;
            }
            List<Map<String, Object>> evidence = new ArrayList<>();
            Set<String> matchScopes = new HashSet<>();
            String classCode = null;

            if (scopes.contains("class") && cls.getFullName().toLowerCase(Locale.ROOT).contains(lower)) {
                matchScopes.add("class");
                evidence.add(Map.of("type", "class", "value", cls.getFullName()));
            }
            if (scopes.contains("method")) {
                String code = cls.getCode();
                for (JavaMethod method : cls.getMethods()) {
                    if (method.getName().toLowerCase(Locale.ROOT).contains(lower)
                            || methodSignature(method).toLowerCase(Locale.ROOT).contains(lower)) {
                        matchScopes.add("method");
                        evidence.add(methodSummary(cls, method, code));
                        if (evidence.size() >= 6) {
                            break;
                        }
                    }
                }
            }
            if (scopes.contains("field")) {
                String code = cls.getCode();
                for (JavaField field : cls.getFields()) {
                    if (field.getName().toLowerCase(Locale.ROOT).contains(lower)
                            || field.getFullName().toLowerCase(Locale.ROOT).contains(lower)) {
                        matchScopes.add("field");
                        evidence.add(fieldSummary(cls, field, code));
                        if (evidence.size() >= 6) {
                            break;
                        }
                    }
                }
            }
            if (scopes.contains("code") || scopes.contains("comment")) {
                classCode = classCode == null ? cls.getCode() : classCode;
                String[] lines = classCode.split("\n", -1);
                for (int i = 0; i < lines.length; i++) {
                    String line = lines[i];
                    if (!line.toLowerCase(Locale.ROOT).contains(lower)) {
                        continue;
                    }
                    String kind = isCommentLine(line) ? "comment" : "code";
                    if (scopes.contains(kind)) {
                        matchScopes.add(kind);
                        evidence.add(Map.of("type", kind, "line", i + 1, "value", line.strip()));
                    } else if (kind.equals("code") && scopes.contains("code")) {
                        matchScopes.add("code");
                        evidence.add(Map.of("type", "code", "line", i + 1, "value", line.strip()));
                    }
                    if (evidence.size() >= 6) {
                        break;
                    }
                }
            }
            if (!evidence.isEmpty()) {
                matches.add(Map.of(
                        "class_name", cls.getFullName(),
                        "package", cls.getPackage(),
                        "match_scopes", new ArrayList<>(matchScopes),
                        "evidence", evidence));
            }
        }
        return page("matches", matches, offset, count, Map.of("ok", true, "search_term", searchTerm, "package", pkg, "search_in", scopes));
    }

    public synchronized Map<String, Object> getSmaliOfClass(String className) {
        JavaClass cls = requireClass(className);
        return Map.of("ok", true, "class_name", className, "smali", cls.getSmali());
    }

    public synchronized Map<String, Object> getAndroidManifest() {
        ensureLoaded();
        return Map.of(
                "ok", true,
                "content", manifestInfo.xml == null ? "" : manifestInfo.xml,
                "package_name", manifestInfo.packageName,
                "application_name", manifestInfo.applicationName,
                "main_activity", manifestInfo.mainActivity);
    }

    public synchronized Map<String, Object> getManifestComponent(String componentType, boolean onlyExported) {
        ensureLoaded();
        if (manifestInfo.xml == null || manifestInfo.xml.isBlank()) {
            return Map.of("ok", false, "error", "Manifest not found");
        }
        List<Map<String, Object>> components = parseManifestComponents(manifestInfo.xml, manifestInfo.packageName, componentType, onlyExported);
        return Map.of("ok", true, "component_type", componentType, "only_exported", onlyExported, "count", components.size(), "components", components);
    }

    public synchronized Map<String, Object> getStrings(int offset, int count) {
        ensureLoaded();
        List<Map<String, Object>> strings = new ArrayList<>();
        for (Map.Entry<String, Path> entry : resourceEntries.entrySet()) {
            if (!entry.getKey().endsWith("strings.xml")) {
                continue;
            }
            try {
                strings.addAll(extractStrings(entry.getKey(), Files.readString(entry.getValue())));
            } catch (Exception ignored) {
            }
        }
        return page("strings", strings, offset, count, Map.of("ok", true));
    }

    public synchronized Map<String, Object> getAllResourceFileNames(int offset, int count) {
        ensureLoaded();
        return page("files", new ArrayList<>(resourceEntries.keySet()), offset, count, Map.of("ok", true));
    }

    public synchronized Map<String, Object> getResourceFile(String name) {
        ensureLoaded();
        Path entry = resourceEntries.get(name);
        if (entry == null) {
            throw new IllegalArgumentException("资源不存在: " + name);
        }
        byte[] bytes;
        try {
            bytes = Files.readAllBytes(entry);
        } catch (Exception e) {
            throw new IllegalArgumentException("读取资源失败: " + e.getMessage());
        }
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("ok", true);
        result.put("resource_name", name);
        if (isProbablyText(name, bytes)) {
            result.put("content_type", "text");
            result.put("content", new String(bytes, java.nio.charset.StandardCharsets.UTF_8));
        } else {
            result.put("content_type", "binary");
            result.put("content_base64", Base64.getEncoder().encodeToString(bytes));
            result.put("size", bytes.length);
        }
        return result;
    }

    public synchronized Map<String, Object> getMainApplicationClassesNames() {
        ensureLoaded();
        String pkg = manifestInfo.packageName == null ? "" : manifestInfo.packageName;
        List<String> filtered = classes.keySet().stream().filter(c -> pkg.isBlank() || c.startsWith(pkg)).toList();
        return Map.of("ok", true, "package_name", pkg, "classes", filtered, "total", filtered.size());
    }

    public synchronized Map<String, Object> getMainApplicationClassesCode(int offset, int count) {
        ensureLoaded();
        String pkg = manifestInfo.packageName == null ? "" : manifestInfo.packageName;
        List<JavaClass> filtered = classes.values().stream().filter(c -> pkg.isBlank() || c.getFullName().startsWith(pkg)).toList();
        List<Map<String, Object>> items = filtered.stream()
                .map(c -> {
                    Map<String, Object> item = new LinkedHashMap<>();
                    item.put("class_name", c.getFullName());
                    item.put("source", c.getCode());
                    return item;
                })
                .collect(Collectors.toList());
        return page("classes", items, offset, count, Map.of("ok", true, "package_name", pkg));
    }

    public synchronized Map<String, Object> getMainActivityClass() {
        ensureLoaded();
        if (manifestInfo.mainActivity == null || manifestInfo.mainActivity.isBlank()) {
            throw new IllegalArgumentException("未识别到 main activity");
        }
        JavaClass cls = classes.get(manifestInfo.mainActivity);
        return Map.of(
                "ok", true,
                "class_name", manifestInfo.mainActivity,
                "source", cls == null ? null : cls.getCode());
    }

    public synchronized Map<String, Object> getPackageTree() {
        ensureLoaded();
        List<Map<String, Object>> pkgs = buildPackageTree();
        return Map.of("ok", true, "total_classes", classes.size(), "total_packages", pkgs.size(), "packages", pkgs);
    }

    public synchronized Map<String, Object> getXrefsToClass(String className, int offset, int count) {
        JavaClass cls = requireClass(className);
        return xrefsForNode(className, cls, offset, count);
    }

    public synchronized Map<String, Object> getXrefsToMethod(String className, String methodName, int offset, int count) {
        JavaClass cls = requireClass(className);
        List<JavaMethod> methods = cls.getMethods().stream().filter(m -> methodMatches(m, methodName)).toList();
        List<Map<String, Object>> refs = new ArrayList<>();
        for (JavaMethod method : methods) {
            refs.addAll(xrefsFor(method));
        }
        refs.sort(Comparator.comparing((Map<String, Object> m) -> String.valueOf(m.get("class_name"))).thenComparingInt(m -> (Integer) m.get("line")));
        return page("references", refs, offset, count, Map.of("ok", true, "target", className + "." + methodName));
    }

    public synchronized Map<String, Object> getXrefsToField(String className, String fieldName, int offset, int count) {
        JavaClass cls = requireClass(className);
        List<JavaField> fields = cls.getFields().stream().filter(f -> f.getName().equals(fieldName) || f.getFullName().endsWith("." + fieldName)).toList();
        List<Map<String, Object>> refs = new ArrayList<>();
        for (JavaField field : fields) {
            refs.addAll(xrefsFor(field));
        }
        refs.sort(Comparator.comparing((Map<String, Object> m) -> String.valueOf(m.get("class_name"))).thenComparingInt(m -> (Integer) m.get("line")));
        return page("references", refs, offset, count, Map.of("ok", true, "target", className + "." + fieldName));
    }

    public synchronized Map<String, Object> renameClass(String className, String newName) {
        JavaClass cls = requireClassFlexible(className);
        String before = cls.getFullName();
        applyRename(new JadxCodeRename(JadxNodeRef.forCls(cls), newName), isResetName(newName), collectReloadClasses(cls), false);
        JavaClass updated = requireClassFlexible(before, cls.getRawName(), newName);
        return Map.of(
                "ok", true,
                "rename_type", "class",
                "input_class_name", className,
                "old_name", before,
                "new_name", updated.getFullName(),
                "raw_name", updated.getRawName(),
                "alias_reset", isResetName(newName));
    }

    public synchronized Map<String, Object> renameMethod(String className, String methodName, String methodShortId, String newName) {
        JavaMethod method = resolveMethodForRename(className, methodName, methodShortId);
        String before = method.getName();
        String signature = methodSignature(method);
        applyRename(new JadxCodeRename(JadxNodeRef.forMth(method), newName), isResetName(newName), collectReloadClasses(method), false);
        JavaMethod updated = resolveMethodByShortId(requireClassFlexible(method.getDeclaringClass().getRawName(), method.getDeclaringClass().getFullName()), method.getMethodNode().getMethodInfo().getShortId());
        return Map.of(
                "ok", true,
                "rename_type", "method",
                "class_name", updated.getDeclaringClass().getFullName(),
                "method_short_id", updated.getMethodNode().getMethodInfo().getShortId(),
                "old_name", before,
                "new_name", updated.getName(),
                "signature", signature,
                "alias_reset", isResetName(newName));
    }

    public synchronized Map<String, Object> renameField(String className, String fieldName, String fieldShortId, String newName) {
        JavaClass cls = requireClassFlexible(className);
        JavaField field = resolveFieldForRename(cls, fieldName, fieldShortId);
        String before = field.getName();
        applyRename(new JadxCodeRename(JadxNodeRef.forFld(field), newName), isResetName(newName), collectReloadClasses(field), false);
        JavaField updated = resolveFieldByShortId(requireClassFlexible(cls.getRawName(), cls.getFullName()), field.getFieldNode().getFieldInfo().getShortId());
        return Map.of(
                "ok", true,
                "rename_type", "field",
                "class_name", updated.getDeclaringClass().getFullName(),
                "field_short_id", updated.getFieldNode().getFieldInfo().getShortId(),
                "old_name", before,
                "new_name", updated.getName(),
                "type", updated.getType().toString(),
                "alias_reset", isResetName(newName));
    }

    public synchronized Map<String, Object> renamePackage(String oldPackageName, String newPackageName) {
        JavaPackage pkg = requirePackage(oldPackageName);
        String before = pkg.getFullName();
        applyRename(new JadxCodeRename(JadxNodeRef.forPkg(pkg.getRawFullName()), newPackageName), isResetName(newPackageName), Set.of(), true);
        JavaPackage updated = requirePackage(before, pkg.getRawFullName(), normalizePackageLookupName(newPackageName));
        return Map.of(
                "ok", true,
                "rename_type", "package",
                "input_package_name", oldPackageName,
                "old_name", before,
                "new_name", updated.getFullName(),
                "raw_name", updated.getRawFullName(),
                "alias_reset", isResetName(newPackageName));
    }

    public synchronized Map<String, Object> renameVariable(String className, String methodName, String methodShortId, String variableName, String newName, String reg, String ssa) {
        JavaMethod method = resolveMethodForRename(className, methodName, methodShortId);
        JavaVariable variable = resolveVariableForRename(method.getDeclaringClass(), method, variableName, reg, ssa);
        String before = variable.getName();
        applyRename(new JadxCodeRename(JadxNodeRef.forMth(method), JadxCodeRef.forVar(variable), newName), isResetName(newName), Set.of(method.getTopParentClass()), false);
        JavaMethod updatedMethod = resolveMethodByShortId(requireClassFlexible(method.getDeclaringClass().getRawName(), method.getDeclaringClass().getFullName()), method.getMethodNode().getMethodInfo().getShortId());
        JavaVariable updatedVariable = resolveVariableByRegSsa(updatedMethod.getDeclaringClass(), updatedMethod, variable.getReg(), variable.getSsa());
        return Map.of(
                "ok", true,
                "rename_type", "variable",
                "class_name", updatedMethod.getDeclaringClass().getFullName(),
                "method_short_id", updatedMethod.getMethodNode().getMethodInfo().getShortId(),
                "method_name", updatedMethod.getName(),
                "old_name", before,
                "new_name", updatedVariable == null ? newName : updatedVariable.getName(),
                "reg", variable.getReg(),
                "ssa", variable.getSsa(),
                "alias_reset", isResetName(newName));
    }

    public synchronized Map<String, Object> listRenames() {
        ensureLoaded();
        ensureCodeData();
        List<Map<String, Object>> items = codeData.getRenames().stream()
                .map(this::renameSummary)
                .collect(Collectors.toList());
        return Map.of("ok", true, "renames", items, "total", items.size());
    }

    public synchronized Map<String, Object> getMethodVariables(String className, String methodName, String methodShortId) {
        JavaMethod method = resolveMethodForRename(className, methodName, methodShortId);
        List<Map<String, Object>> variables = listVariablesForMethod(method.getDeclaringClass(), method).stream()
                .map(var -> {
                    Map<String, Object> item = new LinkedHashMap<>();
                    item.put("class_name", method.getDeclaringClass().getFullName());
                    item.put("method_name", method.getName());
                    item.put("method_short_id", method.getMethodNode().getMethodInfo().getShortId());
                    item.put("variable_name", var.getName());
                    item.put("type", var.getType().toString());
                    item.put("reg", var.getReg());
                    item.put("ssa", var.getSsa());
                    item.put("full_name", var.getFullName());
                    return item;
                })
                .collect(Collectors.toList());
        return Map.of(
                "ok", true,
                "class_name", method.getDeclaringClass().getFullName(),
                "method_name", method.getName(),
                "method_short_id", method.getMethodNode().getMethodInfo().getShortId(),
                "variables", variables,
                "total", variables.size());
    }

    public synchronized Map<String, Object> unsupported(String toolName) {
        return Map.of("ok", false, "tool", toolName, "error", "该能力依赖 GUI/调试态或改名写回，当前 headless 版本未实现。");
    }

    private void applyRename(ICodeRename rename, boolean resetAlias, Set<JavaClass> reloadClasses, boolean reloadAllClasses) {
        ensureCodeData();
        List<ICodeRename> renames = new ArrayList<>(codeData.getRenames());
        renames.remove(rename);
        if (!resetAlias) {
            renames.add(rename);
        }
        renames.sort(ICodeRename::compareTo);
        codeData.setRenames(renames);
        decompiler.getArgs().setCodeData(codeData);
        decompiler.reloadCodeData();

        if (reloadAllClasses) {
            for (JavaClass javaClass : new ArrayList<>(classes.values())) {
                javaClass.reload();
            }
        } else {
            for (JavaClass javaClass : reloadClasses) {
                if (javaClass != null) {
                    javaClass.reload();
                }
            }
        }
        reindexClasses();
    }

    private void ensureCodeData() {
        if (codeData == null) {
            codeData = new JadxCodeData();
            decompiler.getArgs().setCodeData(codeData);
        }
    }

    private void reindexClasses() {
        classes.clear();
        for (JavaClass cls : decompiler.getClassesWithInners()) {
            classes.put(cls.getFullName(), cls);
        }
    }

    private boolean isResetName(String newName) {
        return newName == null || newName.isBlank();
    }

    private Set<JavaClass> collectReloadClasses(JavaNode node) {
        Set<JavaClass> reloadClasses = node.getUseIn().stream()
                .map(useNode -> useNode instanceof JavaClass ? (JavaClass) useNode : useNode.getTopParentClass())
                .filter(Objects::nonNull)
                .collect(Collectors.toCollection(HashSet::new));
        JavaClass owner = node.getTopParentClass();
        if (owner != null) {
            reloadClasses.add(owner);
        }
        return reloadClasses;
    }

    private JavaClass requireClassFlexible(String... names) {
        ensureLoaded();
        for (String name : names) {
            if (name == null || name.isBlank()) {
                continue;
            }
            JavaClass direct = classes.get(name);
            if (direct != null) {
                return direct;
            }
            for (JavaClass cls : classes.values()) {
                if (name.equals(cls.getFullName()) || name.equals(cls.getRawName())) {
                    return cls;
                }
            }
        }
        throw new IllegalArgumentException("类不存在: " + List.of(names));
    }

    private JavaPackage requirePackage(String... names) {
        ensureLoaded();
        for (JavaPackage pkg : decompiler.getPackages()) {
            for (String name : names) {
                if (name == null || name.isBlank()) {
                    continue;
                }
                if (name.equals(pkg.getFullName()) || name.equals(pkg.getRawFullName())) {
                    return pkg;
                }
            }
        }
        throw new IllegalArgumentException("包不存在: " + List.of(names));
    }

    private String normalizePackageLookupName(String name) {
        if (name == null) {
            return null;
        }
        if (name.startsWith(".")) {
            return name.substring(1);
        }
        return name.replace('/', '.');
    }

    private JavaMethod resolveMethodForRename(String className, String methodName, String methodShortId) {
        List<JavaMethod> candidates = new ArrayList<>();
        if (className != null && !className.isBlank()) {
            candidates.addAll(findMethodCandidates(requireClassFlexible(className), methodName));
        } else {
            for (JavaClass cls : classes.values()) {
                candidates.addAll(findMethodCandidates(cls, methodName));
            }
        }
        if (methodShortId != null && !methodShortId.isBlank()) {
            candidates = candidates.stream()
                    .filter(m -> methodShortId.equals(m.getMethodNode().getMethodInfo().getShortId()))
                    .collect(Collectors.toList());
        }
        if (candidates.isEmpty()) {
            throw new IllegalArgumentException("未找到方法: " + methodName + (className == null ? "" : " in " + className));
        }
        if (candidates.size() > 1) {
            throw new IllegalArgumentException("方法不唯一，请提供 class_name 或 method_short_id: " + candidates.stream().map(this::methodLocator).collect(Collectors.joining(", ")));
        }
        return candidates.get(0);
    }

    private List<JavaMethod> findMethodCandidates(JavaClass cls, String methodName) {
        return cls.getMethods().stream()
                .filter(m -> m.getName().equals(methodName)
                        || methodSignature(m).equals(methodName)
                        || m.getMethodNode().getMethodInfo().getShortId().equals(methodName)
                        || m.getFullName().equals(methodName))
                .collect(Collectors.toList());
    }

    private JavaMethod resolveMethodByShortId(JavaClass cls, String shortId) {
        return cls.getMethods().stream()
                .filter(m -> shortId.equals(m.getMethodNode().getMethodInfo().getShortId()))
                .findFirst()
                .orElseThrow(() -> new IllegalArgumentException("方法 shortId 不存在: " + shortId));
    }

    private JavaField resolveFieldForRename(JavaClass cls, String fieldName, String fieldShortId) {
        List<JavaField> matches = cls.getFields().stream()
                .filter(f -> f.getName().equals(fieldName)
                        || f.getFullName().endsWith("." + fieldName)
                        || (fieldShortId != null && fieldShortId.equals(f.getFieldNode().getFieldInfo().getShortId())))
                .collect(Collectors.toList());
        if (fieldShortId != null && !fieldShortId.isBlank()) {
            matches = matches.stream()
                    .filter(f -> fieldShortId.equals(f.getFieldNode().getFieldInfo().getShortId()))
                    .collect(Collectors.toList());
        }
        if (matches.isEmpty()) {
            throw new IllegalArgumentException("未找到字段: " + fieldName + " in " + cls.getFullName());
        }
        if (matches.size() > 1) {
            throw new IllegalArgumentException("字段不唯一，请提供 field_short_id: " + matches.stream().map(this::fieldLocator).collect(Collectors.joining(", ")));
        }
        return matches.get(0);
    }

    private JavaField resolveFieldByShortId(JavaClass cls, String shortId) {
        return cls.getFields().stream()
                .filter(f -> shortId.equals(f.getFieldNode().getFieldInfo().getShortId()))
                .findFirst()
                .orElseThrow(() -> new IllegalArgumentException("字段 shortId 不存在: " + shortId));
    }

    private JavaVariable resolveVariableForRename(JavaClass cls, JavaMethod method, String variableName, String regValue, String ssaValue) {
        Integer reg = parseNullableInt(regValue);
        Integer ssa = parseNullableInt(ssaValue);
        List<JavaVariable> variables = listVariablesForMethod(cls, method);
        if (reg != null && ssa != null) {
            JavaVariable variable = resolveVariableByRegSsa(cls, method, reg, ssa);
            if (variable == null) {
                throw new IllegalArgumentException("未找到变量: r" + reg + "v" + ssa);
            }
            return variable;
        }
        List<JavaVariable> byName = variables.stream()
                .filter(v -> Objects.equals(v.getName(), variableName))
                .collect(Collectors.toList());
        if (byName.isEmpty()) {
            throw new IllegalArgumentException("未找到变量: " + variableName);
        }
        if (byName.size() > 1) {
            throw new IllegalArgumentException("变量名不唯一，请提供 reg 与 ssa: " + byName.stream()
                    .map(v -> v.getName() + "(r" + v.getReg() + "v" + v.getSsa() + ")")
                    .collect(Collectors.joining(", ")));
        }
        return byName.get(0);
    }

    private JavaVariable resolveVariableByRegSsa(JavaClass cls, JavaMethod method, int reg, int ssa) {
        return listVariablesForMethod(cls, method).stream()
                .filter(v -> v.getReg() == reg && v.getSsa() == ssa)
                .findFirst()
                .orElse(null);
    }

    private List<JavaVariable> listVariablesForMethod(JavaClass cls, JavaMethod method) {
        ICodeInfo codeInfo = cls.getCodeInfo();
        Map<Integer, ICodeAnnotation> metadata = codeInfo.getCodeMetadata().getAsMap();
        Map<String, JavaVariable> vars = new LinkedHashMap<>();
        for (Map.Entry<Integer, ICodeAnnotation> entry : metadata.entrySet()) {
            JavaNode node;
            try {
                node = decompiler.getJavaNodeByCodeAnnotation(codeInfo, entry.getValue());
            } catch (Exception ignored) {
                continue;
            }
            if (!(node instanceof JavaVariable variable)) {
                continue;
            }
            if (!variable.getMth().equals(method)) {
                continue;
            }
            vars.putIfAbsent(variable.getReg() + ":" + variable.getSsa(), variable);
        }
        return new ArrayList<>(vars.values());
    }

    private Integer parseNullableInt(String value) {
        if (value == null || value.isBlank()) {
            return null;
        }
        return Integer.parseInt(value);
    }

    private Map<String, Object> renameSummary(ICodeRename rename) {
        Map<String, Object> item = new LinkedHashMap<>();
        String renameType;
        if (rename.getCodeRef() != null) {
            renameType = "variable";
        } else if (rename.getNodeRef().getType() == JadxNodeRef.RefType.PKG) {
            renameType = "package";
        } else {
            renameType = rename.getNodeRef().getType().name().toLowerCase(Locale.ROOT);
        }
        item.put("rename_type", renameType);
        item.put("declaring_class_raw", rename.getNodeRef().getDeclaringClass());
        item.put("short_id", rename.getNodeRef().getShortId());
        item.put("new_name", rename.getNewName());
        if (rename.getCodeRef() != null) {
            item.put("code_ref_type", rename.getCodeRef().getAttachType().name().toLowerCase(Locale.ROOT));
            item.put("code_ref_index", rename.getCodeRef().getIndex());
        }
        return item;
    }

    private String methodLocator(JavaMethod method) {
        return method.getDeclaringClass().getFullName() + "->" + method.getMethodNode().getMethodInfo().getShortId();
    }

    private String fieldLocator(JavaField field) {
        return field.getDeclaringClass().getFullName() + "->" + field.getFieldNode().getFieldInfo().getShortId();
    }

    private void ensureLoaded() {
        if (decompiler == null) {
            throw new IllegalArgumentException("尚未加载 APK，请先调用 load_apk 或启动时传入 --apk");
        }
    }

    private JavaClass requireClass(String className) {
        return requireClassFlexible(className);
    }

    private boolean methodMatches(JavaMethod method, String query) {
        return method.getName().equals(query)
                || method.getFullName().contains(query)
                || methodSignature(method).contains(query);
    }

    private Map<String, Object> methodSummary(JavaClass cls, JavaMethod method, String ownerCode) {
        Map<String, Object> item = new LinkedHashMap<>();
        item.put("class_name", cls.getFullName());
        item.put("method_name", method.getName());
        item.put("method_short_id", method.getMethodNode().getMethodInfo().getShortId());
        item.put("signature", methodSignature(method));
        item.put("full_name", method.getFullName());
        item.put("return_type", method.getReturnType().toString());
        item.put("arguments", method.getArguments().stream().map(Object::toString).toList());
        item.put("line", posToLine(ownerCode, method.getDefPos()));
        return item;
    }

    private Map<String, Object> fieldSummary(JavaClass cls, JavaField field, String ownerCode) {
        Map<String, Object> item = new LinkedHashMap<>();
        item.put("class_name", cls.getFullName());
        item.put("field_name", field.getName());
        item.put("field_short_id", field.getFieldNode().getFieldInfo().getShortId());
        item.put("full_name", field.getFullName());
        item.put("type", field.getType().toString());
        item.put("line", posToLine(ownerCode, field.getDefPos()));
        return item;
    }

    private String methodSignature(JavaMethod method) {
        String args = method.getArguments().stream().map(Object::toString).collect(Collectors.joining(", "));
        return method.getName() + "(" + args + "): " + method.getReturnType();
    }

    private Map<String, Object> xrefsForNode(String targetName, JavaNode node, int offset, int count) {
        List<Map<String, Object>> refs = xrefsFor(node);
        refs.sort(Comparator.comparing((Map<String, Object> m) -> String.valueOf(m.get("class_name"))).thenComparingInt(m -> (Integer) m.get("line")));
        return page("references", refs, offset, count, Map.of("ok", true, "target", targetName));
    }

    private List<Map<String, Object>> xrefsFor(JavaNode target) {
        Set<JavaClass> usageClasses = target.getUseIn().stream()
                .map(node -> node instanceof JavaClass ? (JavaClass) node : node.getTopParentClass())
                .filter(Objects::nonNull)
                .collect(Collectors.toCollection(HashSet::new));

        List<Map<String, Object>> refs = new ArrayList<>();
        for (JavaClass usageClass : usageClasses) {
            ICodeInfo codeInfo = usageClass.getCodeInfo();
            String code = codeInfo.getCodeStr();
            for (Integer pos : usageClass.getUsePlacesFor(codeInfo, target)) {
                int line = posToLine(code, pos);
                refs.add(Map.of(
                        "class_name", usageClass.getFullName(),
                        "line", line,
                        "excerpt", excerpt(code, line),
                        "target", target.getFullName()));
            }
        }
        return refs;
    }

    private List<Map<String, Object>> buildPackageTree() {
        String mainPkg = manifestInfo.packageName == null ? "" : manifestInfo.packageName;
        Map<String, Integer> counts = new HashMap<>();
        for (JavaClass cls : classes.values()) {
            counts.merge(cls.getPackage(), 1, Integer::sum);
        }
        return counts.entrySet().stream()
                .sorted(Map.Entry.<String, Integer>comparingByValue().reversed().thenComparing(Map.Entry.comparingByKey()))
                .map(e -> {
                    Map<String, Object> item = new LinkedHashMap<>();
                    item.put("name", e.getKey());
                    item.put("class_count", e.getValue());
                    item.put("is_likely_library", !mainPkg.isBlank() && !e.getKey().startsWith(mainPkg));
                    return item;
                })
                .collect(Collectors.toList());
    }

    private boolean isProbablyText(String name, byte[] bytes) {
        String lower = name.toLowerCase(Locale.ROOT);
        if (lower.endsWith(".xml") || lower.endsWith(".json") || lower.endsWith(".txt") || lower.endsWith(".html") || lower.endsWith(".js") || lower.endsWith(".css") || lower.endsWith(".properties")) {
            return true;
        }
        int limit = Math.min(bytes.length, 256);
        for (int i = 0; i < limit; i++) {
            byte b = bytes[i];
            if (b == 0) {
                return false;
            }
        }
        return true;
    }

    private ManifestInfo parseManifest(String xml) {
        if (xml == null || xml.isBlank()) {
            return new ManifestInfo(null, null, null, null);
        }
        try {
            Document doc = parseXml(xml);
            Element manifest = doc.getDocumentElement();
            String pkg = manifest.getAttribute("package");
            Element application = firstElement(manifest, "application");
            String appName = application == null ? null : application.getAttributeNS(ANDROID_NS, "name");
            String mainActivity = null;
            if (application != null) {
                for (String tag : List.of("activity", "activity-alias")) {
                    NodeList nodes = application.getElementsByTagName(tag);
                    for (int i = 0; i < nodes.getLength(); i++) {
                        Element activity = (Element) nodes.item(i);
                        if (isMainLauncher(activity)) {
                            mainActivity = normalizeComponent(activity.getAttributeNS(ANDROID_NS, "name"), pkg);
                            break;
                        }
                    }
                    if (mainActivity != null) {
                        break;
                    }
                }
            }
            return new ManifestInfo(xml, pkg, appName, mainActivity);
        } catch (Exception e) {
            return new ManifestInfo(xml, null, null, null);
        }
    }

    private List<Map<String, Object>> parseManifestComponents(String xml, String pkg, String componentType, boolean onlyExported) {
        if (!List.of("activity", "service", "receiver", "provider").contains(componentType)) {
            throw new IllegalArgumentException("不支持的组件类型: " + componentType);
        }
        try {
            Document doc = parseXml(xml);
            Element app = firstElement(doc.getDocumentElement(), "application");
            if (app == null) {
                return Collections.emptyList();
            }
            List<String> tags = new ArrayList<>();
            tags.add(componentType);
            if (componentType.equals("activity")) {
                tags.add("activity-alias");
            }
            List<Map<String, Object>> result = new ArrayList<>();
            for (String tag : tags) {
                NodeList nodes = app.getElementsByTagName(tag);
                for (int i = 0; i < nodes.getLength(); i++) {
                    Element element = (Element) nodes.item(i);
                    String exportedRaw = element.getAttributeNS(ANDROID_NS, "exported");
                    boolean exported = exportedRaw.isBlank() ? element.getElementsByTagName("intent-filter").getLength() > 0 : Boolean.parseBoolean(exportedRaw);
                    if (onlyExported && !exported) {
                        continue;
                    }
                    result.add(Map.of(
                            "type", tag,
                            "name", normalizeComponent(element.getAttributeNS(ANDROID_NS, "name"), pkg),
                            "exported", exported,
                            "permission", blankToNull(element.getAttributeNS(ANDROID_NS, "permission"))));
                }
            }
            return result;
        } catch (Exception e) {
            throw new IllegalArgumentException("Manifest 解析失败: " + e.getMessage());
        }
    }

    private List<Map<String, Object>> extractStrings(String file, String xml) {
        try {
            Document doc = parseXml(xml);
            NodeList nodes = doc.getDocumentElement().getElementsByTagName("string");
            List<Map<String, Object>> result = new ArrayList<>();
            for (int i = 0; i < nodes.getLength(); i++) {
                Element el = (Element) nodes.item(i);
                result.add(Map.of(
                        "file", file,
                        "name", el.getAttribute("name"),
                        "text", el.getTextContent().strip()));
            }
            return result;
        } catch (Exception e) {
            return Collections.emptyList();
        }
    }

    private Document parseXml(String xml) throws Exception {
        DocumentBuilderFactory factory = DocumentBuilderFactory.newInstance();
        factory.setNamespaceAware(true);
        factory.setFeature("http://apache.org/xml/features/disallow-doctype-decl", true);
        factory.setFeature("http://xml.org/sax/features/external-general-entities", false);
        factory.setFeature("http://xml.org/sax/features/external-parameter-entities", false);
        return factory.newDocumentBuilder().parse(new InputSource(new StringReader(xml)));
    }

    private Element firstElement(Element parent, String tag) {
        NodeList list = parent.getElementsByTagName(tag);
        return list.getLength() == 0 ? null : (Element) list.item(0);
    }

    private boolean isMainLauncher(Element activity) {
        NodeList intents = activity.getElementsByTagName("intent-filter");
        for (int i = 0; i < intents.getLength(); i++) {
            Element intent = (Element) intents.item(i);
            boolean hasMain = false;
            boolean hasLauncher = false;
            NodeList actions = intent.getElementsByTagName("action");
            for (int j = 0; j < actions.getLength(); j++) {
                Element action = (Element) actions.item(j);
                if ("android.intent.action.MAIN".equals(action.getAttributeNS(ANDROID_NS, "name"))) {
                    hasMain = true;
                }
            }
            NodeList categories = intent.getElementsByTagName("category");
            for (int j = 0; j < categories.getLength(); j++) {
                Element category = (Element) categories.item(j);
                if ("android.intent.category.LAUNCHER".equals(category.getAttributeNS(ANDROID_NS, "name"))) {
                    hasLauncher = true;
                }
            }
            if (hasMain && hasLauncher) {
                return true;
            }
        }
        return false;
    }

    private String normalizeComponent(String raw, String pkg) {
        if (raw == null || raw.isBlank()) {
            return raw;
        }
        if (raw.startsWith(".")) {
            return pkg + raw;
        }
        if (!raw.contains(".")) {
            return pkg.isBlank() ? raw : pkg + "." + raw;
        }
        return raw;
    }

    private Set<String> parseScopes(String searchIn) {
        return java.util.Arrays.stream(searchIn.split(","))
                .map(String::trim)
                .filter(s -> !s.isBlank())
                .collect(Collectors.toCollection(HashSet::new));
    }

    private boolean isCommentLine(String line) {
        String stripped = line.stripLeading();
        return stripped.startsWith("//") || stripped.startsWith("/*") || stripped.startsWith("*");
    }

    private String blankToNull(String value) {
        return value == null || value.isBlank() ? null : value;
    }

    private Map<String, Object> page(String key, List<?> items, int offset, int count) {
        return page(key, items, offset, count, Map.of("ok", true));
    }

    private Map<String, Object> page(String key, List<?> items, int offset, int count, Map<String, Object> base) {
        int from = Math.max(0, offset);
        int to = count <= 0 ? items.size() : Math.min(items.size(), from + count);
        List<?> sliced = from >= items.size() ? List.of() : items.subList(from, to);
        Map<String, Object> result = new LinkedHashMap<>(base);
        result.put(key, sliced);
        result.put("offset", from);
        result.put("count", sliced.size());
        result.put("total", items.size());
        return result;
    }

    private int posToLine(String text, int pos) {
        if (text == null || text.isEmpty()) {
            return 1;
        }
        int line = 1;
        int end = Math.min(Math.max(0, pos), text.length());
        for (int i = 0; i < end; i++) {
            if (text.charAt(i) == '\n') {
                line++;
            }
        }
        return line;
    }

    private String excerpt(String text, int line) {
        String[] lines = text.split("\n", -1);
        int start = Math.max(1, line - 2);
        int end = Math.min(lines.length, line + 2);
        List<String> out = new ArrayList<>();
        for (int i = start; i <= end; i++) {
            out.add(i + ": " + lines[i - 1]);
        }
        return String.join("\n", out);
    }

    private int countLines(String text) {
        return text == null || text.isEmpty() ? 0 : text.split("\n", -1).length;
    }

    private String buildProjectId(Path apkPath) throws Exception {
        byte[] content = java.nio.file.Files.readAllBytes(apkPath);
        byte[] digest = MessageDigest.getInstance("SHA-256").digest(content);
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < 6; i++) {
            sb.append(String.format("%02x", digest[i]));
        }
        return apkPath.getFileName().toString().replaceAll("\\.apk$", "") + "-" + sb;
    }

    public synchronized void close() {
        if (decompiler != null) {
            decompiler.close();
        }
        if (tempDir != null) {
            try (var walk = Files.walk(tempDir)) {
                walk.sorted(Comparator.reverseOrder()).forEach(path -> {
                    try { Files.deleteIfExists(path); } catch (Exception ignored) {}
                });
            } catch (Exception ignored) {
            }
        }
        decompiler = null;
        currentApk = null;
        currentProjectId = null;
        loadedAt = null;
        manifestInfo = null;
        tempDir = null;
        resourcesDir = null;
        classes.clear();
        resourceEntries.clear();
    }

    private record ManifestInfo(String xml, String packageName, String applicationName, String mainActivity) {
    }

}
