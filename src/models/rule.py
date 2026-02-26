"""WRD API — Pydantic schemas for Rule resources."""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class RulesetInfo(BaseModel):
    version: str
    commit_hash: Optional[str] = None
    branch: str
    rules_count: int
    decoders_count: int
    size_bytes: int
    last_synced: Optional[datetime] = None
    etag: Optional[str] = None


class RulesetList(BaseModel):
    current_version: str
    git_remote: str
    branch: str
    rulesets: List[RulesetInfo]


class GitSyncRequest(BaseModel):
    branch: Optional[str] = Field(default=None, description="Override branch to pull from")
    force: bool = Field(default=False, description="Force pull even if no changes detected")


class GitSyncResponse(BaseModel):
    status: str  # success | no_changes | error
    branch: str
    commit_hash: str
    rules_count: int
    decoders_count: int
    message: str
    synced_at: datetime
