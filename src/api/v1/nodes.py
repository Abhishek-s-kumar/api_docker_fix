"""WRD API — Node-specific endpoints: rule pull + status reporting."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Request, Response, status
from fastapi.responses import StreamingResponse

from src.api.deps import AuthKey, DBSession, NodeAuthKey
from src.models.node import NodeStatusReport, NodeStatusResponse
from src.services.rule_service import RuleService
from src.services.sync_service import SyncOrchestrator

router = APIRouter(prefix="/nodes", tags=["Nodes"])


@router.get(
    "/{node_id}/rules",
    summary="Pull rules package for a specific node",
    response_description="ZIP archive of all rules and decoders",
    responses={
        200: {"content": {"application/zip": {}}},
        304: {"description": "No changes since last pull (ETag match)"},
    },
)
async def get_node_rules(
    node_id: str,
    request: Request,
    api_key: NodeAuthKey,
    if_none_match: str | None = Header(default=None, alias="If-None-Match"),
) -> Response:
    """
    Download the current rules package as a ZIP archive.

    Supports HTTP caching via ETag — if the client sends `If-None-Match` with
    the current ETag, returns `304 Not Modified` instead of the full package.
    This dramatically reduces bandwidth for nodes that are already up-to-date.
    """
    rule_svc = RuleService()

    # Get current git info to determine version
    from src.utils.git_sync import GitOpsController

    git = GitOpsController()
    repo_info = await git.get_repo_info()
    version = repo_info.get("commit", "HEAD")

    # Build package (calculates ETag)
    zip_data, etag = rule_svc.build_rules_package(version)

    if if_none_match and if_none_match.strip('"') == etag:
        return Response(status_code=304)

    return Response(
        content=zip_data,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="rules-{version[:8]}.zip"',
            "ETag": f'"{etag}"',
            "X-Ruleset-Version": version,
            "X-Node-Id": node_id,
        },
    )


@router.post(
    "/{node_id}/status",
    response_model=NodeStatusResponse,
    summary="Report sync status (called by Wazuh nodes)",
)
async def report_node_status(
    node_id: str,
    body: NodeStatusReport,
    db: DBSession,
    api_key: NodeAuthKey,
) -> NodeStatusResponse:
    """
    Wazuh manager nodes call this endpoint to report the result of
    a rule synchronization attempt. Updates the node's sync status in
    the database and marks the deployment node record as complete.
    """
    # Find the cluster this node belongs to
    from sqlalchemy import select
    from src.db.base import ClusterNode

    result = await db.execute(
        select(ClusterNode).where(ClusterNode.node_id == node_id, ClusterNode.is_active == True)
    )
    node = result.scalar_one_or_none()

    if not node:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Node '{node_id}' not found or not registered",
        )

    # Update node status
    orchestrator = SyncOrchestrator(db)
    await orchestrator.update_node_status(
        cluster_id=node.cluster_id,
        node_id=node_id,
        status=body.status.value,
        deployed_version=body.deployed_version,
        error_details=body.error_details,
    )

    return NodeStatusResponse(
        node_id=node_id,
        cluster_id=node.cluster_id,
        status=body.status.value,
        message=f"Status updated to '{body.status.value}'",
        updated_at=datetime.now(timezone.utc),
    )


@router.delete(
    "/{node_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Deregister a node",
)
async def deregister_node(
    node_id: str,
    db: DBSession,
    api_key: NodeAuthKey,
) -> Response:
    """Soft-delete a node from its cluster."""
    from sqlalchemy import select
    from src.db.base import ClusterNode

    result = await db.execute(
        select(ClusterNode).where(ClusterNode.node_id == node_id)
    )
    node = result.scalar_one_or_none()
    if not node:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Node '{node_id}' not found",
        )
    node.is_active = False
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
