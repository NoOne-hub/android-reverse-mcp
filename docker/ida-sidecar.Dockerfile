FROM root1/idapro:9.3-cli-mcp

COPY docker/ida-sidecar-entrypoint.sh /usr/local/bin/ida-sidecar-entrypoint
RUN chmod +x /usr/local/bin/ida-sidecar-entrypoint

ENTRYPOINT ["/usr/local/bin/ida-sidecar-entrypoint"]
