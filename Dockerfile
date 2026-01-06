FROM python:3.12-slim AS base

WORKDIR /app

# Install uv for fast package management
RUN pip install --no-cache-dir uv

# Copy all source files needed for build
COPY pyproject.toml README.md ./
COPY homelab_mcp/ homelab_mcp/

# Install package (non-editable for production)
RUN uv pip install --system .

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash appuser && \
    chown -R appuser:appuser /app
USER appuser

# Expose MCP server port
EXPOSE 6971

# Health check - verify MCP endpoint responds
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python -c "import socket; s=socket.socket(); s.settimeout(5); s.connect(('localhost', 6971)); s.close()" || exit 1

# Run the server
CMD ["python", "-m", "homelab_mcp.main"]
