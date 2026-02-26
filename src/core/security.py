"""WRD API — Security: JWT tokens and API key management."""
from __future__ import annotations

import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from passlib.context import CryptContext

from src.config import get_settings

settings = get_settings()

# Bcrypt context for API key hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ── API Key Operations ────────────────────────────────────────────────────────

def generate_api_key(prefix: str = "wrd") -> str:
    """Generate a new random API key with a prefix."""
    token = secrets.token_urlsafe(32)
    return f"{prefix}_{token}"


def hash_api_key(key: str) -> str:
    """Hash an API key for storage (bcrypt)."""
    return pwd_context.hash(key)


def verify_api_key(plain_key: str, hashed_key: str) -> bool:
    """Verify an API key against its bcrypt hash."""
    return pwd_context.verify(plain_key, hashed_key)


def generate_node_key(cluster_name: str, node_id: str) -> str:
    """Generate a deterministic node-specific API key."""
    token = secrets.token_urlsafe(24)
    return f"node_{cluster_name}_{node_id}_{token}"


# ── JWT Operations ───────────────────────────────────────────────────────────

def create_access_token(
    subject: str,
    role: str = "reader",
    expires_delta: timedelta | None = None,
) -> str:
    """Create a signed JWT access token."""
    if expires_delta is None:
        expires_delta = timedelta(minutes=settings.jwt_expire_minutes)

    expire = datetime.now(timezone.utc) + expires_delta
    payload = {
        "sub": subject,
        "role": role,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict:
    """Decode and validate a JWT token. Raises JWTError on failure."""
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])


# ── Admin Bootstrap ──────────────────────────────────────────────────────────

def ensure_data_dir() -> None:
    """Ensure the /data directory exists for admin key persistence."""
    os.makedirs(os.path.dirname(settings.admin_key_file), exist_ok=True)


def save_admin_key(key: str) -> None:
    """Persist admin key to the configured file."""
    ensure_data_dir()
    with open(settings.admin_key_file, "w") as f:
        f.write(key)
    os.chmod(settings.admin_key_file, 0o600)


def load_admin_key() -> str | None:
    """Load admin key from file if it exists."""
    try:
        with open(settings.admin_key_file) as f:
            return f.read().strip()
    except FileNotFoundError:
        return None
