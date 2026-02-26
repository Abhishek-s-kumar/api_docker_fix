"""WRD API — Pydantic v2 schemas for Cluster resources."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class TopologyType(str, Enum):
    single = "single"
    multi_master = "multi-master"
    master_worker = "master-worker"


class NodeType(str, Enum):
    master = "master"
    worker = "worker"


class SyncStatus(str, Enum):
    pending = "pending"
    syncing = "syncing"
    synced = "synced"
    failed = "failed"
    unknown = "unknown"


# ── Site / Node config (for registration) ────────────────────────────────────

class SiteConfig(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, examples=["frankfurt"])
    node_count: int = Field(default=1, ge=1, le=100)
    location: Optional[str] = Field(default=None, examples=["eu-central-1"])
    master_node_id: Optional[str] = Field(default=None, examples=["wazuh-master-fra"])
    worker_node_ids: Optional[List[str]] = Field(default=None)


# ── Cluster Registration ──────────────────────────────────────────────────────

class ClusterCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=255, examples=["production-emea"])
    topology_type: TopologyType = Field(default=TopologyType.master_worker)
    description: Optional[str] = Field(default=None)
    sites: List[SiteConfig] = Field(default_factory=list)


class NodeCredential(BaseModel):
    node_id: str
    node_type: NodeType
    site: Optional[str]
    api_key: str  # Only shown once on creation


class ClusterCreateResponse(BaseModel):
    cluster_id: UUID
    name: str
    topology_type: TopologyType
    nodes: List[NodeCredential]
    message: str = "Cluster registered. Store node API keys securely — they will not be shown again."


# ── Cluster Read ──────────────────────────────────────────────────────────────

class NodeSummary(BaseModel):
    id: UUID
    node_id: str
    node_type: NodeType
    site: Optional[str]
    region: Optional[str]
    sync_status: SyncStatus
    ruleset_version: Optional[str]
    last_seen: Optional[datetime]
    is_active: bool

    model_config = {"from_attributes": True}


class ClusterRead(BaseModel):
    id: UUID
    name: str
    topology_type: TopologyType
    description: Optional[str]
    is_active: bool
    node_count: int
    nodes: List[NodeSummary]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ClusterList(BaseModel):
    total: int
    clusters: List[ClusterRead]


# ── Sync Trigger ──────────────────────────────────────────────────────────────

class RolloutStrategy(str, Enum):
    rolling = "rolling"
    blue_green = "blue-green"
    canary = "canary"
    immediate = "immediate"


class SyncTriggerRequest(BaseModel):
    ruleset_version: Optional[str] = Field(
        default=None,
        description="Git tag/branch/commit to deploy. Defaults to HEAD of configured branch.",
        examples=["v1.5.0"],
    )
    strategy: RolloutStrategy = Field(default=RolloutStrategy.rolling)
    batch_size: int = Field(default=1, ge=1, le=50)
    dry_run: bool = Field(default=False)


class SyncTriggerResponse(BaseModel):
    deployment_id: UUID
    cluster_id: UUID
    status: str
    ruleset_version: str
    strategy: RolloutStrategy
    estimated_nodes: int
    message: str
