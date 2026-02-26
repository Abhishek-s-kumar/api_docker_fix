"""WRD API — Sync orchestrator: rolling, blue-green, canary deployments."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.db.base import Cluster, ClusterNode, DeploymentNode, RuleDeployment
from src.models.cluster import RolloutStrategy, SyncTriggerRequest, SyncTriggerResponse
from src.services.rule_service import RuleService
from src.utils.git_sync import GitOpsController


class SyncOrchestrator:
    """Orchestrates rule distribution across nodes."""

    def __init__(
        self,
        db: AsyncSession,
        rule_service: Optional[RuleService] = None,
    ) -> None:
        self._db = db
        self._rules = rule_service or RuleService()

    async def trigger_sync(
        self,
        cluster_id: UUID,
        request: SyncTriggerRequest,
        initiated_by: str = "api",
    ) -> SyncTriggerResponse:
        """
        Trigger a rule deployment across all nodes in a cluster.
        Creates a RuleDeployment record and dispatches the sync event.
        """
        # Fetch cluster + nodes
        result = await self._db.execute(
            select(Cluster)
            .options(selectinload(Cluster.nodes))
            .where(Cluster.id == cluster_id, Cluster.is_active == True)
        )
        cluster = result.scalar_one_or_none()
        if not cluster:
            raise ValueError(f"Cluster {cluster_id} not found or inactive")

        active_nodes = [n for n in cluster.nodes if n.is_active]
        if not active_nodes:
            raise ValueError(f"Cluster {cluster_id} has no active nodes")

        # Determine ruleset version
        git = GitOpsController()
        repo_info = await git.get_repo_info()
        version = request.ruleset_version or repo_info.get("commit", "HEAD")

        if request.dry_run:
            return SyncTriggerResponse(
                deployment_id=UUID("00000000-0000-0000-0000-000000000000"),
                cluster_id=cluster_id,
                status="dry_run",
                ruleset_version=version,
                strategy=request.strategy,
                estimated_nodes=len(active_nodes),
                message=f"[DRY RUN] Would deploy {version} to {len(active_nodes)} nodes using {request.strategy} strategy.",
            )

        # Create deployment record
        deployment = RuleDeployment(
            cluster_id=cluster_id,
            initiated_by=initiated_by,
            ruleset_version=version,
            rollout_strategy=request.strategy.value,
            status="in_progress",
        )
        self._db.add(deployment)
        await self._db.flush()

        # Create per-node records
        for node in active_nodes:
            dn = DeploymentNode(
                deployment_id=deployment.id,
                node_id=node.id,
                status="pending",
            )
            self._db.add(dn)

        await self._db.commit()
        await self._db.refresh(deployment)

        # Background execution (don't await — fire and forget)
        asyncio.create_task(
            self._execute_deployment(
                deployment_id=deployment.id,
                nodes=active_nodes,
                version=version,
                strategy=request.strategy,
                batch_size=request.batch_size,
            )
        )

        return SyncTriggerResponse(
            deployment_id=deployment.id,
            cluster_id=cluster_id,
            status="in_progress",
            ruleset_version=version,
            strategy=request.strategy,
            estimated_nodes=len(active_nodes),
            message=f"Deployment started. Use /deployments/{deployment.id} to track progress.",
        )

    async def _execute_deployment(
        self,
        deployment_id: UUID,
        nodes: List[ClusterNode],
        version: str,
        strategy: RolloutStrategy,
        batch_size: int,
    ) -> None:
        """
        Internal deployment runner. Executes based on rollout strategy.
        Nodes report back their own status via POST /nodes/{id}/status.
        """
        if strategy == RolloutStrategy.rolling:
            await self._rolling_deploy(deployment_id, nodes, version, batch_size)
        elif strategy == RolloutStrategy.immediate:
            await self._immediate_deploy(deployment_id, nodes, version)
        else:
            # blue_green / canary also trigger via event bus
            await self._immediate_deploy(deployment_id, nodes, version)

    async def _rolling_deploy(
        self,
        deployment_id: UUID,
        nodes: List[ClusterNode],
        version: str,
        batch_size: int,
    ) -> None:
        """Rolling deployment: workers first, then masters."""
        workers = [n for n in nodes if n.node_type == "worker"]
        masters = [n for n in nodes if n.node_type == "master"]
        ordered = workers + masters

        for i in range(0, len(ordered), batch_size):
            batch = ordered[i : i + batch_size]
            for node in batch:
                await self._mark_node_deploying(deployment_id, node.id)
            await asyncio.sleep(2)  # Brief pause between batches

    async def _immediate_deploy(
        self, deployment_id: UUID, nodes: List[ClusterNode], version: str
    ) -> None:
        """Immediate: all nodes simultaneously."""
        for node in nodes:
            await self._mark_node_deploying(deployment_id, node.id)

    async def _mark_node_deploying(self, deployment_id: UUID, node_db_id: UUID) -> None:
        """Mark a specific node as deploying in the database."""
        result = await self._db.execute(
            select(DeploymentNode).where(
                DeploymentNode.deployment_id == deployment_id,
                DeploymentNode.node_id == node_db_id,
            )
        )
        dn = result.scalar_one_or_none()
        if dn:
            dn.status = "deploying"
            dn.started_at = datetime.now(timezone.utc)
            await self._db.commit()

    async def update_node_status(
        self,
        cluster_id: UUID,
        node_id: str,
        status: str,
        deployed_version: Optional[str],
        error_details: Optional[str],
    ) -> None:
        """Called when a node reports back its sync result."""
        result = await self._db.execute(
            select(ClusterNode).where(
                ClusterNode.cluster_id == cluster_id,
                ClusterNode.node_id == node_id,
            )
        )
        node = result.scalar_one_or_none()
        if node:
            node.sync_status = status
            node.last_seen = datetime.now(timezone.utc)
            if deployed_version:
                node.ruleset_version = deployed_version
            await self._db.commit()
