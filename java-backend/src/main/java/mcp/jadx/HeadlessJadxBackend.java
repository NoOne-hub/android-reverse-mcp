package mcp.jadx;

import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;

import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.Executors;

public class HeadlessJadxBackend {
    private static final Gson GSON = new GsonBuilder().disableHtmlEscaping().create();

    public static void main(String[] args) throws Exception {
        Map<String, String> cli = parseArgs(args);
        String host = cli.getOrDefault("host", "127.0.0.1");
        int port = Integer.parseInt(cli.getOrDefault("port", "8650"));
        int threads = Integer.parseInt(cli.getOrDefault("threads", String.valueOf(Math.max(2, Runtime.getRuntime().availableProcessors() / 2))));
        String apkPath = cli.get("apk");

        AnalyzerService analyzer = new AnalyzerService(threads);
        if (apkPath != null && !apkPath.isBlank()) {
            analyzer.loadApk(Path.of(apkPath));
        }

        HttpServer server = HttpServer.create(new InetSocketAddress(host, port), 0);
        server.createContext("/", exchange -> handle(exchange, analyzer));
        server.setExecutor(Executors.newCachedThreadPool());
        server.start();
        System.err.printf("headless-jadx-backend listening on http://%s:%d%n", host, port);
    }

    private static void handle(HttpExchange exchange, AnalyzerService analyzer) throws IOException {
        try {
            String method = exchange.getRequestMethod();
            URI uri = exchange.getRequestURI();
            String path = uri.getPath();
            Map<String, String> params = parseQuery(uri.getRawQuery());

            Object response;
            if (!"GET".equalsIgnoreCase(method) && !"POST".equalsIgnoreCase(method)) {
                sendJson(exchange, 405, Map.of("ok", false, "error", "Method not allowed"));
                return;
            }

            response = switch (path) {
                case "/health" -> analyzer.health();
                case "/load-apk" -> analyzer.loadApk(Path.of(required(params, "apk_path")));
                case "/current-project" -> analyzer.currentProject();
                case "/list-projects" -> analyzer.listProjects();
                case "/select-project" -> analyzer.unsupported("select_project");
                case "/all-classes" -> analyzer.getAllClasses(getInt(params, "offset", 0), getInt(params, "count", 0));
                case "/class-source" -> analyzer.getClassSource(required(params, "class_name"));
                case "/methods-of-class" -> analyzer.getMethodsOfClass(required(params, "class_name"));
                case "/fields-of-class" -> analyzer.getFieldsOfClass(required(params, "class_name"));
                case "/method-by-name" -> analyzer.getMethodByName(required(params, "class_name"), required(params, "method_name"));
                case "/search-method" -> analyzer.searchMethodByName(required(params, "method_name"));
                case "/search-classes" -> analyzer.searchClassesByKeyword(
                        required(params, "search_term"),
                        params.getOrDefault("package", ""),
                        params.getOrDefault("search_in", "code"),
                        getInt(params, "offset", 0),
                        getInt(params, "count", 20));
                case "/smali-of-class" -> analyzer.getSmaliOfClass(required(params, "class_name"));
                case "/manifest" -> analyzer.getAndroidManifest();
                case "/manifest-component" -> analyzer.getManifestComponent(required(params, "component_type"), getBool(params, "only_exported", false));
                case "/strings" -> analyzer.getStrings(getInt(params, "offset", 0), getInt(params, "count", 0));
                case "/list-all-resource-files-names" -> analyzer.getAllResourceFileNames(getInt(params, "offset", 0), getInt(params, "count", 0));
                case "/get-resource-file" -> analyzer.getResourceFile(required(params, "file_name"));
                case "/main-application-classes-names" -> analyzer.getMainApplicationClassesNames();
                case "/main-application-classes-code" -> analyzer.getMainApplicationClassesCode(getInt(params, "offset", 0), getInt(params, "count", 0));
                case "/main-activity" -> analyzer.getMainActivityClass();
                case "/package-tree" -> analyzer.getPackageTree();
                case "/xrefs-to-class" -> analyzer.getXrefsToClass(required(params, "class_name"), getInt(params, "offset", 0), getInt(params, "count", 20));
                case "/xrefs-to-method" -> analyzer.getXrefsToMethod(required(params, "class_name"), required(params, "method_name"), getInt(params, "offset", 0), getInt(params, "count", 20));
                case "/xrefs-to-field" -> analyzer.getXrefsToField(required(params, "class_name"), required(params, "field_name"), getInt(params, "offset", 0), getInt(params, "count", 20));
                case "/rename-class" -> analyzer.renameClass(required(params, "class_name"), required(params, "new_name"));
                case "/rename-method" -> analyzer.renameMethod(params.get("class_name"), required(params, "method_name"), params.get("method_short_id"), required(params, "new_name"));
                case "/rename-field" -> analyzer.renameField(required(params, "class_name"), required(params, "field_name"), params.get("field_short_id"), required(params, "new_name"));
                case "/rename-package" -> analyzer.renamePackage(required(params, "old_package_name"), required(params, "new_package_name"));
                case "/rename-variable" -> analyzer.renameVariable(required(params, "class_name"), required(params, "method_name"), params.get("method_short_id"), required(params, "variable_name"), required(params, "new_name"), params.get("reg"), params.get("ssa"));
                case "/list-renames" -> analyzer.listRenames();
                case "/method-variables" -> analyzer.getMethodVariables(required(params, "class_name"), required(params, "method_name"), params.get("method_short_id"));
                case "/debug/stack-frames" -> analyzer.unsupported("debug_get_stack_frames");
                case "/debug/threads" -> analyzer.unsupported("debug_get_threads");
                case "/debug/variables" -> analyzer.unsupported("debug_get_variables");
                default -> Map.of("ok", false, "error", "Unknown path: " + path);
            };
            sendJson(exchange, 200, response);
        } catch (IllegalArgumentException e) {
            sendJson(exchange, 400, Map.of("ok", false, "error", e.getMessage()));
        } catch (Exception e) {
            sendJson(exchange, 500, Map.of("ok", false, "error", e.getClass().getSimpleName() + ": " + e.getMessage()));
        } finally {
            exchange.close();
        }
    }

    private static void sendJson(HttpExchange exchange, int status, Object body) throws IOException {
        byte[] data = GSON.toJson(body).getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set("Content-Type", "application/json; charset=utf-8");
        exchange.sendResponseHeaders(status, data.length);
        try (OutputStream os = exchange.getResponseBody()) {
            os.write(data);
        }
    }

    private static String required(Map<String, String> params, String key) {
        String value = params.get(key);
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("Missing required param: " + key);
        }
        return value;
    }

    private static int getInt(Map<String, String> params, String key, int def) {
        String value = params.get(key);
        return value == null || value.isBlank() ? def : Integer.parseInt(value);
    }

    private static boolean getBool(Map<String, String> params, String key, boolean def) {
        String value = params.get(key);
        return value == null || value.isBlank() ? def : Boolean.parseBoolean(value);
    }

    private static Map<String, String> parseArgs(String[] args) {
        Map<String, String> map = new HashMap<>();
        for (int i = 0; i < args.length; i++) {
            String arg = args[i];
            if (arg.startsWith("--")) {
                String key = arg.substring(2);
                String value = "true";
                if (i + 1 < args.length && !args[i + 1].startsWith("--")) {
                    value = args[++i];
                }
                map.put(key, value);
            }
        }
        return map;
    }

    private static Map<String, String> parseQuery(String query) {
        Map<String, String> result = new HashMap<>();
        if (query == null || query.isBlank()) {
            return result;
        }
        for (String part : query.split("&")) {
            if (part.isBlank()) {
                continue;
            }
            String[] kv = part.split("=", 2);
            String key = decode(kv[0]);
            String value = kv.length > 1 ? decode(kv[1]) : "";
            result.put(key, value);
        }
        return result;
    }

    private static String decode(String value) {
        return URLDecoder.decode(value, StandardCharsets.UTF_8);
    }
}
