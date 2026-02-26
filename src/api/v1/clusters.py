"""WRD API — Cluster management endpoints."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, Response, status

from src.api.deps import AdminKey, AuthKey, DBSession, WriterKey
from src.models.cluster import (
    ClusterCreate,
    ClusterCreateResponse,
    ClusterList,
    ClusterRead,
    SyncTriggerRequest,
    SyncTriggerResponse,
)
from src.services.cluster_service import ClusterService
from src.services.sync_service import SyncOrchestrator

router = APIRouter(prefix="/clusters", tags=["Clusters"])


@router.post(
    "",
    response_model=ClusterCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new Wazuh cluster",
)
async def register_cluster(
    data: ClusterCreate,
    db: DBSession,
    api_key: AdminKey,
) -> ClusterCreateResponse:
    """
    Register a new Wazuh cluster. Generates unique API keys for each node.

    **Important:** Node API keys are only shown once — store them securely.
    """
    service = ClusterService(db)
    try:
        return await service.register_cluster(data)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@router.get(
    "",
    response_model=ClusterList,
    summary="List all registered clusters",
)
async def list_clusters(
    db: DBSession,
    api_key: AuthKey,
    skip: int = 0,
    limit: int = 50,
    active_only: bool = True,
) -> ClusterList:
    """Return all registered Wazuh clusters with their node summaries."""
    service = ClusterService(db)
    return await service.list_clusters(skip=skip, limit=limit, active_only=active_only)


@router.get(
    "/{cluster_id}",
    response_model=ClusterRead,
    summary="Get cluster details",
)
async def get_cluster(
    cluster_id: UUID,
    db: DBSession,
    api_key: AuthKey,
) -> ClusterRead:
    """Return detailed info for a specific cluster including all node statuses."""
    service = ClusterService(db)
    cluster = await service.get_cluster(cluster_id)
    if not cluster:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Cluster {cluster_id} not found",
        )
    return cluster


@router.delete(
    "/{cluster_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Deregister a cluster",
)
async def delete_cluster(
    cluster_id: UUID,
    db: DBSession,
    api_key: AdminKey,
) -> Response:
    """Soft-delete a cluster (marks as inactive, retains history)."""
    service = ClusterService(db)
    deleted = await service.delete_cluster(cluster_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Cluster {cluster_id} not found",
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{cluster_id}/sync",
    response_model=SyncTriggerResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger rule synchronization across cluster",
)
async def trigger_sync(
    cluster_id: UUID,
    request: SyncTriggerRequest,
    db: DBSession,
    api_key: WriterKey,
) -> SyncTriggerResponse:
    """
    Trigger a rule distribution job across all active nodes in the cluster.

    Supports three rollout strategies:
    - **rolling**: Workers first, then masters, in batches
    - **blue-green**: Deploy to secondary environment, then switch
    - **canary**: Gradual rollout with health gate
    - **immediate**: All nodes simultaneously

    Use `dry_run: true` to preview without making changes.
    """
    orchestrator = SyncOrchestrator(db)
    try:
        return await orchestrator.trigger_sync(
            cluster_id=cluster_id,
            request=request,
            initiated_by=api_key.name,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
