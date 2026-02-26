"""WRD API — Cluster service: registration, node key generation, health."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.security import generate_node_key, hash_api_key
from src.db.base import Cluster, ClusterNode, RuleDeployment
from src.models.cluster import (
    ClusterCreate,
    ClusterCreateResponse,
    ClusterList,
    ClusterRead,
    NodeCredential,
    NodeSummary,
    NodeType,
    SiteConfig,
    SyncStatus,
)


class ClusterService:
    """Business logic for Wazuh cluster management."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def register_cluster(self, data: ClusterCreate) -> ClusterCreateResponse:
        """
        Register a new Wazuh cluster. Generates unique API keys per node.
        Returns cluster info with plaintext API keys (shown once only).
        """
        # Check uniqueness
        existing = await self._db.execute(
            select(Cluster).where(Cluster.name == data.name)
        )
        if existing.scalar_one_or_none():
            raise ValueError(f"Cluster '{data.name}' already exists")

        cluster = Cluster(
            name=data.name,
            topology_type=data.topology_type.value,
            description=data.description,
        )
        self._db.add(cluster)
        await self._db.flush()  # get cluster.id

        # Generate nodes from site configs
        credentials: List[NodeCredential] = []

        if data.sites:
            for site in data.sites:
                credentials.extend(
                    await self._create_site_nodes(cluster, site)
                )
        else:
            # Default: create a single master node
            cred = await self._create_node(cluster, "master-01", NodeType.master, None)
            credentials.append(cred)

        await self._db.commit()
        await self._db.refresh(cluster)

        return ClusterCreateResponse(
            cluster_id=cluster.id,
            name=cluster.name,
            topology_type=data.topology_type,
            nodes=credentials,
        )

    async def _create_site_nodes(
        self, cluster: Cluster, site: SiteConfig
    ) -> List[NodeCredential]:
        credentials = []

        # Master node
        if site.master_node_id:
            cred = await self._create_node(
                cluster, site.master_node_id, NodeType.master, site.name
            )
            credentials.append(cred)
        elif cluster.topology_type in ("master-worker", "multi-master"):
            master_id = f"{site.name}-master"
            cred = await self._create_node(cluster, master_id, NodeType.master, site.name)
            credentials.append(cred)

        # Worker nodes
        worker_ids = site.worker_node_ids or [
            f"{site.name}-worker-{i:02d}" for i in range(1, site.node_count)
        ]
        for wid in worker_ids:
            cred = await self._create_node(cluster, wid, NodeType.worker, site.name)
            credentials.append(cred)

        return credentials

    async def _create_node(
        self, cluster: Cluster, node_id: str, node_type: NodeType, site: Optional[str]
    ) -> NodeCredential:
        raw_key = generate_node_key(cluster.name, node_id)
        node = ClusterNode(
            cluster_id=cluster.id,
            node_id=node_id,
            node_type=node_type.value,
            site=site,
            api_key_hash=hash_api_key(raw_key),
        )
        self._db.add(node)
        return NodeCredential(
            node_id=node_id,
            node_type=node_type,
            site=site,
            api_key=raw_key,
        )

    async def get_cluster(self, cluster_id: UUID) -> Optional[ClusterRead]:
        result = await self._db.execute(
            select(Cluster)
            .options(selectinload(Cluster.nodes))
            .where(Cluster.id == cluster_id)
        )
        cluster = result.scalar_one_or_none()
        if not cluster:
            return None
        return self._to_read(cluster)

    async def list_clusters(
        self, skip: int = 0, limit: int = 50, active_only: bool = True
    ) -> ClusterList:
        q = select(Cluster).options(selectinload(Cluster.nodes))
        if active_only:
            q = q.where(Cluster.is_active == True)
        q = q.offset(skip).limit(limit).order_by(Cluster.created_at.desc())
        result = await self._db.execute(q)
        clusters = result.scalars().all()

        # Count total
        count_result = await self._db.execute(select(Cluster).where(Cluster.is_active == True))
        total = len(count_result.scalars().all())

        return ClusterList(
            total=total,
            clusters=[self._to_read(c) for c in clusters],
        )

    async def delete_cluster(self, cluster_id: UUID) -> bool:
        result = await self._db.execute(
            select(Cluster).where(Cluster.id == cluster_id)
        )
        cluster = result.scalar_one_or_none()
        if not cluster:
            return False
        cluster.is_active = False
        await self._db.commit()
        return True

    @staticmethod
    def _to_read(cluster: Cluster) -> ClusterRead:
        nodes = [
            NodeSummary(
                id=n.id,
                node_id=n.node_id,
                node_type=NodeType(n.node_type),
                site=n.site,
                region=n.region,
                sync_status=SyncStatus(n.sync_status),
                ruleset_version=n.ruleset_version,
                last_seen=n.last_seen,
                is_active=n.is_active,
            )
            for n in cluster.nodes
        ]
        return ClusterRead(
            id=cluster.id,
            name=cluster.name,
            topology_type=cluster.topology_type,
            description=cluster.description,
            is_active=cluster.is_active,
            node_count=len(nodes),
            nodes=nodes,
            created_at=cluster.created_at,
            updated_at=cluster.updated_at,
        )
