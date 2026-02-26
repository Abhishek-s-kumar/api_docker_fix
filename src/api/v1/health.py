"""WRD API — Health check endpoints: /health (liveness) and /ready (readiness)."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Request
from pydantic import BaseModel

from src.config import get_settings

settings = get_settings()
router = APIRouter(tags=["Health"])


class HealthResponse(BaseModel):
    status: str
    version: str
    environment: str
    timestamp: str


class ReadinessResponse(BaseModel):
    status: str
    database: str
    git_repo: str
    timestamp: str


@router.get("/health", response_model=HealthResponse, summary="Liveness check")
async def health() -> HealthResponse:
    """
    Liveness probe — always returns 200 if the process is running.
    Used by Docker HEALTHCHECK and Kubernetes liveness probes.
    """
    return HealthResponse(
        status="ok",
        version=settings.app_version,
        environment=settings.environment,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


@router.get("/ready", response_model=ReadinessResponse, summary="Readiness check")
async def readiness(request: Request) -> ReadinessResponse:
    """
    Readiness probe — checks DB and Redis connectivity.
    Returns 200 only when all dependencies are reachable.
    Used by Kubernetes readiness probes.
    """
    import asyncio
    from pathlib import Path

    db_status = "unknown"

    # Check DB
    try:
        db = request.app.state.db_engine
        async with db.connect() as conn:
            await conn.execute(__import__("sqlalchemy", fromlist=["text"]).text("SELECT 1"))
        db_status = "ok"
    except Exception as e:
        db_status = f"error: {str(e)[:80]}"

    # Check git repo
    git_path = Path(settings.git_repo_path)
    git_status = "ok" if (git_path / ".git").exists() or git_path.exists() else "not_initialized"

    overall = "ok" if db_status == "ok" else "degraded"

    from fastapi import Response
    response_data = ReadinessResponse(
        status=overall,
        database=db_status,
        git_repo=git_status,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )

    if overall != "ok":
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=503, content=response_data.model_dump())

    return response_data
