FROM maven:3.9.9-eclipse-temurin-17 AS java-builder
WORKDIR /build
COPY java-backend /build
RUN mvn -DskipTests package

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APK_MCP_WORKSPACE=/workspace \
    JADX_BACKEND_JAR=/opt/headless-jadx/backend/headless-jadx-backend-0.1.0.jar \
    JADX_ALL_JAR=/opt/headless-jadx/backend/jadx-1.5.5-all.jar \
    JADX_BACKEND_HOST=127.0.0.1 \
    JADX_BACKEND_PORT=8650

RUN apt-get update && apt-get install -y --no-install-recommends \
    openjdk-21-jre-headless \
    ca-certificates \
    apktool \
    apksigner \
    zipalign \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml README.md /app/
COPY src /app/src
RUN pip install --no-cache-dir .

RUN mkdir -p /opt/headless-jadx/backend /input /workspace
COPY --from=java-builder /build/target/headless-jadx-backend-0.1.0.jar /opt/headless-jadx/backend/
COPY --from=java-builder /build/lib/jadx-1.5.5-all.jar /opt/headless-jadx/backend/

EXPOSE 8651
VOLUME ["/workspace", "/input"]
ENTRYPOINT ["android_reverse_mcp"]
CMD ["--http", "--host", "0.0.0.0", "--port", "8651"]
