FROM python:3.12-slim
ARG GHIDRA_VERSION=12.0.4
ARG GHIDRA_RELEASE_DATE=20260303
ARG DEBIAN_MIRROR=https://mirrors.ustc.edu.cn/debian
ARG DEBIAN_SECURITY_MIRROR=https://mirrors.ustc.edu.cn/debian-security
ARG HTTP_PROXY=
ARG HTTPS_PROXY=
ARG ALL_PROXY=
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive \
    GHIDRA_INSTALL_DIR=/opt/ghidra/ghidra_${GHIDRA_VERSION}_PUBLIC \
    UV_LINK_MODE=copy \
    VIRTUAL_ENV=/opt/android-reverse-mcp-venv \
    PATH=/opt/android-reverse-mcp-venv/bin:$PATH

RUN sed -i "s|http://deb.debian.org/debian|${DEBIAN_MIRROR}|g; s|http://deb.debian.org/debian-security|${DEBIAN_SECURITY_MIRROR}|g" /etc/apt/sources.list.d/debian.sources \
 && printf 'Acquire::Retries "5";\nAcquire::http::Timeout "60";\nAcquire::https::Timeout "60";\n' > /etc/apt/apt.conf.d/99retries \
 && apt-get update \
 && apt-get install -y --no-install-recommends \
    openjdk-21-jdk-headless \
    ca-certificates \
    unzip \
  && rm -rf /var/lib/apt/lists/*

COPY third_party/ghidra_12.0.4_PUBLIC_20260303.zip /tmp/ghidra.zip
RUN mkdir -p /opt/ghidra \
 && unzip -q /tmp/ghidra.zip -d /opt/ghidra \
 && rm -f /tmp/ghidra.zip

WORKDIR /app
COPY third_party /app/third_party
COPY docker/ghidra-sidecar-entrypoint.sh /usr/local/bin/ghidra-sidecar-entrypoint
RUN chmod +x /usr/local/bin/ghidra-sidecar-entrypoint \
 && pip install --no-cache-dir uv \
 && uv venv "$VIRTUAL_ENV" \
 && uv pip install --python "$VIRTUAL_ENV/bin/python" /app/third_party/ghidra-headless-mcp-b9c491a6383dbc68c581e7fed16341ac47e7faba.zip

ENTRYPOINT ["/usr/local/bin/ghidra-sidecar-entrypoint"]
