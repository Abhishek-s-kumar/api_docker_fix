"""WRD API — GitOps controller: async git operations + rule validation."""
from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any, Dict, Optional

from src.config import get_settings

settings = get_settings()


class GitOpsController:
    """
    Manages the local rules Git repository.
    Uses subprocess so as not to block the async event loop.
    """

    def __init__(self, repo_path: Optional[str] = None) -> None:
        self._repo_path = Path(repo_path or settings.git_repo_path)

    # ── Internal helpers ──────────────────────────────────────────────────────

    async def _run_git(self, *args: str) -> tuple[int, str, str]:
        """Run a git command asynchronously."""
        proc = await asyncio.create_subprocess_exec(
            "git",
            *args,
            cwd=str(self._repo_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        return proc.returncode, stdout.decode().strip(), stderr.decode().strip()

    async def _ensure_repo(self) -> None:
        """Clone the repo if it doesn't exist, or verify it's a git repo."""
        git_dir = self._repo_path / ".git"
        if not git_dir.exists():
            self._repo_path.mkdir(parents=True, exist_ok=True)
            if settings.git_remote_url:
                code, out, err = await asyncio.create_subprocess_exec(
                    "git", "clone", settings.git_remote_url, str(self._repo_path),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                ) and (0, "", "")
                # Actually clone properly
                proc = await asyncio.create_subprocess_exec(
                    "git", "clone", settings.git_remote_url, ".",
                    cwd=str(self._repo_path),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                await proc.communicate()
            else:
                # Init a local repo for development
                proc = await asyncio.create_subprocess_exec(
                    "git", "init",
                    cwd=str(self._repo_path),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                await proc.communicate()
                # Create placeholder structure
                for sub in ["rules", "decoders", "lists"]:
                    (self._repo_path / sub).mkdir(exist_ok=True)
                    placeholder = self._repo_path / sub / ".gitkeep"
                    placeholder.touch(exist_ok=True)

    # ── Public API ────────────────────────────────────────────────────────────

    async def sync_repository(
        self,
        branch: Optional[str] = None,
        force: bool = False,
        verify_signatures: bool = False,
    ) -> Dict[str, Any]:
        """
        Pull latest rules from the remote Git repository.
        Returns a dict with status, branch, commit, message.
        """
        await self._ensure_repo()
        target_branch = branch or settings.git_branch

        # Fetch
        code, _, err = await self._run_git("fetch", "origin")
        if code != 0 and not (self._repo_path / ".git" / "refs" / "heads").exists():
            return {
                "status": "no_remote",
                "branch": target_branch,
                "commit": "local",
                "message": "Local repo only — no remote configured.",
            }

        # Get current commit before pull
        _, before_commit, _ = await self._run_git("rev-parse", "HEAD")

        # Checkout and pull
        await self._run_git("checkout", target_branch)
        pull_args = ["pull", "origin", target_branch]
        if force:
            pull_args = ["reset", "--hard", f"origin/{target_branch}"]
        code, out, err = await self._run_git(*pull_args)

        # Get new commit
        _, after_commit, _ = await self._run_git("rev-parse", "HEAD")

        if before_commit == after_commit and not force:
            return {
                "status": "no_changes",
                "branch": target_branch,
                "commit": after_commit,
                "message": "Repository already up to date.",
            }

        return {
            "status": "success",
            "branch": target_branch,
            "commit": after_commit,
            "message": f"Pulled {target_branch}: {before_commit[:8]}→{after_commit[:8]}",
        }

    async def get_repo_info(self) -> Dict[str, str]:
        """Return current branch, commit, and optional tag."""
        await self._ensure_repo()
        _, commit, _ = await self._run_git("rev-parse", "HEAD")
        _, branch, _ = await self._run_git("rev-parse", "--abbrev-ref", "HEAD")
        _, tag, _ = await self._run_git("describe", "--tags", "--exact-match", "HEAD")

        return {
            "commit": commit or "unknown",
            "branch": branch or settings.git_branch,
            "tag": tag or "",
        }

    async def validate_ruleset(self, rules_path: Optional[Path] = None) -> Dict[str, Any]:
        """
        Validate XML syntax of all rule files.
        Returns a validation report.
        """
        from src.utils.validators import validate_xml_files

        path = rules_path or self._repo_path
        return await validate_xml_files(path)
