# ─────────────────────────────────────────────
# Stage 1: Build stage
# ─────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    git \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python build tools
COPY pyproject.toml README.md ./
COPY src/ ./src/

RUN pip install --upgrade pip && \
    pip install --no-cache-dir hatchling && \
    pip install --no-cache-dir "bcrypt==3.2.0" "."

# ─────────────────────────────────────────────
# Stage 2: Production image
# ─────────────────────────────────────────────
FROM python:3.11-slim AS production

LABEL org.opencontainers.image.title="WRD API"
LABEL org.opencontainers.image.version="2.0.0"
LABEL org.opencontainers.image.description="Wazuh Rules Distribution API"

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Set up application directory
WORKDIR /app

# Copy dependencies from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Patch passlib to avoid bcrypt version check error using sed - use | as delimiter
# We target the specific line in bcrypt.py
RUN sed -i 's|_bcrypt\.__about__\.__version__|getattr(_bcrypt, "__version__", "3.2.0")|g' /usr/local/lib/python3.11/site-packages/passlib/handlers/bcrypt.py

# Create non-root user
RUN groupadd -r wrdapi && useradd -r -g wrdapi wrdapi

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
ENTRYPOINT ["gunicorn", "src.main:app", \
     "--worker-class", "uvicorn.workers.UvicornWorker", \
     "--workers", "4", \
     "--bind", "0.0.0.0:8000", \
     "--timeout", "120", \
     "--keep-alive", "5", \
     "--access-logfile", "-", \
     "--error-logfile", "-"]
