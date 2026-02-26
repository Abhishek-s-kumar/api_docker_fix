"""
WRD API v2.0.0 — FastAPI Application Factory
Centralized GitOps-based rules management for distributed Wazuh clusters.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.api.v1 import clusters, health, nodes, rules
from src.config import get_settings
from src.db.session import engine

settings = get_settings()

# ── Structured logging ────────────────────────────────────────────────────────
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.stdlib.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    logger_factory=structlog.stdlib.LoggerFactory(),
)
log = structlog.get_logger()


# ── Application lifespan ──────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Startup: store engine reference.
    Shutdown: close all connections cleanly.
    """
    log.info("wrd_api.startup", version=settings.app_version, env=settings.environment)

    app.state.db_engine = engine

    # Ensure /data directory exists for admin key file
    import os
    os.makedirs(os.path.dirname(settings.admin_key_file), exist_ok=True)

    log.info("wrd_api.ready")
    yield

    # Teardown
    await engine.dispose()
    log.info("wrd_api.shutdown")


# ── Application factory ───────────────────────────────────────────────────────
def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        description=(
            "Centralized GitOps-based rules management API for distributed Wazuh clusters. "
            "Supports multi-node deployments with rolling, blue-green, and canary update strategies."
        ),
        version=settings.app_version,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # ── CORS ──────────────────────────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=settings.cors_allow_credentials,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Global exception handlers ──────────────────────────────────────────────
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        log.error("unhandled_exception", path=request.url.path, error=str(exc), exc_info=True)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "Internal server error", "path": str(request.url.path)},
        )

    # ── Routers ───────────────────────────────────────────────────────────────
    # Health checks at root level (no /api/v1 prefix for k8s probes)
    app.include_router(health.router)

    # API v1 routes
    api_prefix = "/api/v1"
    app.include_router(clusters.router, prefix=api_prefix)
    app.include_router(nodes.router, prefix=api_prefix)
    app.include_router(rules.router, prefix=api_prefix)

    # ── Root redirect ─────────────────────────────────────────────────────────
    @app.get("/", include_in_schema=False)
    async def root():
        return {
            "name": settings.app_name,
            "version": settings.app_version,
            "docs": "/docs",
            "health": "/health",
            "ready": "/ready",
            "api": "/api/v1",
        }

    return app


# Create the app instance
app = create_app()
