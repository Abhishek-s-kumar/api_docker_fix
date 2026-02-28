"""WRD API — FastAPI dependency injection: DB, Redis, auth."""
from __future__ import annotations

import re
from collections.abc import AsyncGenerator
from typing import Annotated, Optional

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import get_settings
from src.core.security import verify_api_key
from src.db.base import APIKey, ClusterNode
from src.db.session import AsyncSessionLocal

settings = get_settings()

# ── Database ──────────────────────────────────────────────────────────────────

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async database session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()




# ── Authentication ────────────────────────────────────────────────────────────

def _extract_bearer_token(authorization: Optional[str]) -> Optional[str]:
    """Extract token from 'Bearer <token>' header."""
    if not authorization:
        return None
    match = re.match(r"^Bearer\s+(.+)$", authorization, re.IGNORECASE)
    return match.group(1) if match else None


async def require_api_key(
    authorization: Annotated[Optional[str], Header()] = None,
    db: AsyncSession = Depends(get_db),
) -> APIKey:
    """
    Validate an API key from the Authorization header.
    Raises 401 if missing/invalid, 403 if inactive.
    """
    token = _extract_bearer_token(authorization)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header. Use: Authorization: Bearer <api_key>",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Load all active keys and verify against bcrypt hash
    result = await db.execute(select(APIKey).where(APIKey.is_active == True))
    keys = result.scalars().all()

    matched_key: Optional[APIKey] = None
    for api_key in keys:
        try:
            if verify_api_key(token, api_key.key_hash):
                matched_key = api_key
                break
        except Exception:
            continue

    if not matched_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return matched_key


async def require_admin(api_key: APIKey = Depends(require_api_key)) -> APIKey:
    """Require admin role."""
    if api_key.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Admin role required. Your key has role: '{api_key.role}'",
        )
    return api_key


async def require_writer(api_key: APIKey = Depends(require_api_key)) -> APIKey:
    """Require admin or writer role."""
    if api_key.role not in ("admin", "writer"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Writer or admin role required",
        )
    return api_key


# ── Type aliases for cleaner endpoint signatures ───────────────────────────────

DBSession = Annotated[AsyncSession, Depends(get_db)]
AuthKey = Annotated[APIKey, Depends(require_api_key)]
AdminKey = Annotated[APIKey, Depends(require_admin)]
WriterKey = Annotated[APIKey, Depends(require_writer)]

async def require_node_key(
    authorization: Annotated[Optional[str], Header()] = None,
    db: AsyncSession = Depends(get_db),
) -> ClusterNode:
    token = _extract_bearer_token(authorization)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )
    result = await db.execute(select(ClusterNode).where(ClusterNode.is_active == True))
    nodes = result.scalars().all()
    matched_node = None
    for n in nodes:
        try:
            if verify_api_key(token, n.api_key_hash):
                matched_node = n
                break
        except Exception:
            continue
    if not matched_node:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return matched_node

NodeAuthKey = Annotated[ClusterNode, Depends(require_node_key)]
