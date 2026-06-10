FROM python:3.11-slim

# Node.js required for Phoenix MCP server (npx @arizeai/phoenix-mcp)
RUN apt-get update && apt-get install -y --no-install-recommends \
    nodejs npm curl \
    && rm -rf /var/lib/apt/lists/*

# Pre-install the Phoenix MCP server so npx resolves locally instead of
# downloading on the first /scan (30-60s penalty on a cold instance).
# Version must match settings.phoenix_mcp_package in core/config.py.
RUN npm install -g @arizeai/phoenix-mcp@4.0.8 && npm cache clean --force

WORKDIR /app

# Install Python dependencies first (cache layer)
COPY pyproject.toml .
RUN pip install --no-cache-dir -e . && pip cache purge

# Copy application code
COPY . .

# Non-root user for security
RUN useradd -m -u 1001 iris && chown -R iris:iris /app
USER iris

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8080/status || exit 1

CMD ["uvicorn", "core.main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]
