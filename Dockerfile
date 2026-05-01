FROM maven:3.9.9-eclipse-temurin-17 AS java-builder
WORKDIR /build
COPY java-backend /build
RUN mvn -DskipTests package

FROM python:3.12-slim
ARG GHIDRA_VERSION=12.0.4
ARG GHIDRA_RELEASE_DATE=20260303
ARG GHIDRA_MCP_REF=b9c491a6383dbc68c581e7fed16341ac47e7faba
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive \
    APK_MCP_WORKSPACE=/workspace \
    JADX_BACKEND_JAR=/opt/headless-jadx/backend/headless-jadx-backend-0.1.0.jar \
    JADX_ALL_JAR=/opt/headless-jadx/backend/jadx-1.5.5-all.jar \
    JADX_BACKEND_HOST=127.0.0.1 \
    JADX_BACKEND_PORT=8650 \
    GHIDRA_INSTALL_DIR=/opt/ghidra/ghidra_${GHIDRA_VERSION}_PUBLIC \
    GHIDRA_BACKEND_HOST=127.0.0.1 \
    GHIDRA_BACKEND_PORT=8765 \
    UV_LINK_MODE=copy \
    VIRTUAL_ENV=/opt/android-reverse-mcp-venv \
    PATH=/opt/android-reverse-mcp-venv/bin:/app/bin:$PATH

RUN apt-get update && apt-get install -y --no-install-recommends \
    openjdk-21-jdk-headless \
    ca-certificates \
    curl \
    unzip \
    apksigner \
    zipalign \
  && rm -rf /var/lib/apt/lists/*

RUN mkdir -p /opt/ghidra \
 && curl -L --fail \
      -o /tmp/ghidra.zip \
      "https://github.com/NationalSecurityAgency/ghidra/releases/download/Ghidra_${GHIDRA_VERSION}_build/ghidra_${GHIDRA_VERSION}_PUBLIC_${GHIDRA_RELEASE_DATE}.zip" \
 && unzip -q /tmp/ghidra.zip -d /opt/ghidra \
 && rm -f /tmp/ghidra.zip

WORKDIR /app
COPY pyproject.toml README.md /app/
COPY src /app/src
COPY bin /app/bin
COPY third_party /app/third_party
RUN chmod +x /app/bin/apktool /app/bin/docker-entrypoint \
 && pip install --no-cache-dir uv \
 && uv venv "$VIRTUAL_ENV" \
 && uv pip install --python "$VIRTUAL_ENV/bin/python" . \
 && curl -L --fail \
      -o /tmp/ghidra-headless-mcp.zip \
      "https://codeload.github.com/mrphrazer/ghidra-headless-mcp/zip/${GHIDRA_MCP_REF}" \
 && uv pip install --python "$VIRTUAL_ENV/bin/python" /tmp/ghidra-headless-mcp.zip \
 && rm -f /tmp/ghidra-headless-mcp.zip

RUN mkdir -p /opt/headless-jadx/backend /input /workspace
COPY --from=java-builder /build/target/headless-jadx-backend-0.1.0.jar /opt/headless-jadx/backend/
COPY --from=java-builder /build/lib/jadx-1.5.5-all.jar /opt/headless-jadx/backend/

EXPOSE 8651
VOLUME ["/workspace", "/input"]
ENTRYPOINT ["/app/bin/docker-entrypoint"]
CMD []
