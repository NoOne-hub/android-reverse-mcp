FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    VIRTUAL_ENV=/opt/ida-pro-mcp-venv \
    PATH=/opt/ida-pro-mcp-venv/bin:$PATH

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
  && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv \
 && uv venv /opt/ida-pro-mcp-venv \
 && uv pip install --python /opt/ida-pro-mcp-venv/bin/python https://github.com/mrexodia/ida-pro-mcp/archive/refs/heads/main.zip

COPY ida-sidecar/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

VOLUME ["/workspace", "/opt/ida-pro", "/root/.idapro"]
EXPOSE 8745
ENTRYPOINT ["/entrypoint.sh"]
