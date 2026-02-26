"""WRD API — Pydantic schemas for Node resources."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class NodeSyncStatus(str, Enum):
    success = "success"
    failed = "failed"
    partial = "partial"
    pending = "pending"


class NodeStatusReport(BaseModel):
    """Payload sent by a node to report its sync status."""
    status: NodeSyncStatus
    deployed_version: Optional[str] = Field(default=None)
    error_details: Optional[str] = Field(default=None)
    rules_count: Optional[int] = Field(default=None, ge=0)


class NodeStatusResponse(BaseModel):
    node_id: str
    cluster_id: UUID
    status: str
    message: str
    updated_at: datetime
