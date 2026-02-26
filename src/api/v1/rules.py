"""WRD API — Rules management endpoints."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from src.api.deps import AuthKey, WriterKey
from src.models.rule import GitSyncRequest, GitSyncResponse, RulesetList
from src.services.rule_service import RuleService
from src.utils.git_sync import GitOpsController

router = APIRouter(prefix="/rules", tags=["Rules"])


@router.get(
    "",
    response_model=RulesetList,
    summary="List available rulesets",
)
async def list_rulesets(api_key: AuthKey) -> RulesetList:
    """
    Return metadata about the current ruleset in the Git repository.
    Includes counts of rule files, decoders, and the current git version.
    """
    rule_svc = RuleService()
    return await rule_svc.list_rulesets()


@router.post(
    "/sync-git",
    response_model=GitSyncResponse,
    summary="Pull latest rules from Git repository",
)
async def sync_from_git(
    request: GitSyncRequest,
    api_key: WriterKey,
) -> GitSyncResponse:
    """
    Trigger a manual Git pull to update the local rules repository.

    - Pulls from the configured remote URL and branch
    - Validates XML syntax of all pulled files
    - Returns the new commit hash and rule counts

    **Tip:** This is separate from syncing to Wazuh nodes.
    After pulling, use `POST /clusters/{id}/sync` to push rules to nodes.
    """
    rule_svc = RuleService()
    return await rule_svc.sync_from_git(branch=request.branch, force=request.force)


@router.post(
    "/validate",
    summary="Validate current ruleset XML syntax",
)
async def validate_ruleset(api_key: AuthKey) -> dict:
    """
    Run XML validation on all rule files in the current repository.
    Returns a detailed report of any syntax errors found.
    """
    git = GitOpsController()
    return await git.validate_ruleset()
