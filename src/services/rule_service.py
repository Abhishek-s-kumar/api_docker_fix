"""WRD API — Rule service: ruleset listing, packaging, ETag management."""
from __future__ import annotations

import hashlib
import io
import os
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from src.config import get_settings
from src.models.rule import GitSyncResponse, RulesetInfo, RulesetList
from src.utils.git_sync import GitOpsController

settings = get_settings()


class RuleService:
    """Business logic for rule package management."""

    def __init__(self, git_controller: Optional[GitOpsController] = None) -> None:
        self._git = git_controller or GitOpsController()
        self._rules_path = Path(settings.rules_base_path)
        self._package_dir = Path(settings.rules_package_dir)
        self._package_dir.mkdir(parents=True, exist_ok=True)

    async def list_rulesets(self) -> RulesetList:
        """Return current ruleset info from the git repository."""
        info = await self._git.get_repo_info()
        rules_count, decoders_count, size_bytes = self._count_rules()

        ruleset = RulesetInfo(
            version=info.get("tag", info.get("commit", "unknown")),
            commit_hash=info.get("commit"),
            branch=info.get("branch", settings.git_branch),
            rules_count=rules_count,
            decoders_count=decoders_count,
            size_bytes=size_bytes,
            last_synced=datetime.now(timezone.utc),
        )
        return RulesetList(
            current_version=ruleset.version,
            git_remote=settings.git_remote_url,
            branch=settings.git_branch,
            rulesets=[ruleset],
        )

    async def sync_from_git(
        self, branch: Optional[str] = None, force: bool = False
    ) -> GitSyncResponse:
        """Pull latest rules from Git and return sync result."""
        result = await self._git.sync_repository(branch=branch, force=force)
        rules_count, decoders_count, _ = self._count_rules()
        return GitSyncResponse(
            status=result["status"],
            branch=result["branch"],
            commit_hash=result["commit"],
            rules_count=rules_count,
            decoders_count=decoders_count,
            message=result["message"],
            synced_at=datetime.now(timezone.utc),
        )

    def build_rules_package(self, version: str) -> tuple[bytes, str]:
        """
        Build a ZIP package of all rules and decoders.
        Returns (zip_bytes, etag).
        """
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            for base_dir in ["rules", "decoders", "lists"]:
                src_dir = self._rules_path / base_dir
                if src_dir.exists():
                    for file_path in src_dir.rglob("*.xml"):
                        zf.write(file_path, str(file_path.relative_to(self._rules_path)))
                    for file_path in src_dir.rglob("*.cdb"):
                        zf.write(file_path, str(file_path.relative_to(self._rules_path)))

            # Write version manifest
            zf.writestr(
                "MANIFEST.txt",
                f"version={version}\nbuilt_at={datetime.now(timezone.utc).isoformat()}\n",
            )

        data = buf.getvalue()
        etag = hashlib.sha256(data).hexdigest()
        return data, etag

    def _count_rules(self) -> tuple[int, int, int]:
        """Count rule files, decoder files, and total bytes."""
        rules_count = 0
        decoders_count = 0
        total_size = 0

        for xml_file in self._rules_path.rglob("*.xml"):
            total_size += xml_file.stat().st_size
            if "decoder" in str(xml_file).lower():
                decoders_count += 1
            else:
                rules_count += 1

        return rules_count, decoders_count, total_size
