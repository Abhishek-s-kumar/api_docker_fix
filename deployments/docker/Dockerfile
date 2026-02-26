# ─────────────────────────────────────────────
# Stage 1: Build dependencies
# ─────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build

# Install build tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY pyproject.toml .
COPY README.md .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir hatchling && \
    pip install --no-cache-dir ".[dev]" --target /deps

# ─────────────────────────────────────────────
# Stage 2: Production image
# ─────────────────────────────────────────────
FROM python:3.11-slim AS production

LABEL org.opencontainers.image.title="WRD API"
LABEL org.opencontainers.image.version="2.0.0"
LABEL org.opencontainers.image.description="Wazuh Rules Distribution API"

# Runtime dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Non-root user
RUN groupadd -r wrdapi && useradd -r -g wrdapi -d /app wrdapi

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /deps /usr/local/lib/python3.11/site-packages

# Copy application source
COPY src/ /app/src/
COPY migrations/ /app/migrations/
COPY alembic.ini /app/alembic.ini
COPY scripts/ /app/scripts/

# Create required runtime directories
RUN mkdir -p /app/git-repo /data /tmp/rule-packages && \
    chown -R wrdapi:wrdapi /app /data /tmp/rule-packages

USER wrdapi

# Expose API port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Default: Gunicorn with Uvicorn workers
CMD ["python", "-m", "gunicorn", \
     "src.main:app", \
     "--worker-class", "uvicorn.workers.UvicornWorker", \
     "--workers", "4", \
     "--bind", "0.0.0.0:8000", \
     "--timeout", "120", \
     "--keep-alive", "5", \
     "--access-logfile", "-", \
     "--error-logfile", "-", \
     "--log-level", "info"]
