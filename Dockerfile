FROM python:3.11-slim

WORKDIR /app

# Install uv for fast package management
RUN pip install uv

# Copy dependency files
COPY pyproject.toml .
COPY README.md .

# Install dependencies
RUN uv pip install --system -e .

# Copy application code
COPY homelab_mcp/ homelab_mcp/
COPY config.yaml* ./

# Expose MCP server port
EXPOSE 6971

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:6971/health')" || exit 1

# Run the server
CMD ["python", "-m", "homelab_mcp.main"]
