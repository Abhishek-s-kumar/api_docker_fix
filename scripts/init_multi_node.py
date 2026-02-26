#!/usr/bin/env python3
"""
WRD API — Multi-node initialization script.
Runs DB migrations and creates the first admin API key.

Usage:
    python scripts/init_multi_node.py --create-admin
    python scripts/init_multi_node.py --create-admin --non-interactive
"""
from __future__ import annotations

import asyncio
import os
import sys

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import argparse
import subprocess
from datetime import datetime, timezone

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()
app = typer.Typer()


async def _run_migrations() -> bool:
    """Run Alembic migrations."""
    console.print("[blue]→[/blue] Running database migrations...")
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        console.print(f"[red]✗ Migration failed:[/red] {result.stderr}")
        return False
    console.print("[green]✓[/green] Migrations complete")
    return True


async def _create_admin_key(name: str = "admin") -> str:
    """Create an admin API key in the database."""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from src.config import get_settings
    from src.core.security import generate_api_key, hash_api_key, save_admin_key
    from src.db.base import APIKey

    settings = get_settings()

    engine = create_async_engine(settings.database_url, echo=False)
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    raw_key = generate_api_key("admin")
    key_hash = hash_api_key(raw_key)

    async with async_session() as session:
        # Check if admin key already exists
        from sqlalchemy import select
        result = await session.execute(select(APIKey).where(APIKey.name == name))
        existing = result.scalar_one_or_none()

        if existing:
            console.print(f"[yellow]⚠[/yellow]  Admin key '{name}' already exists — generating new key")
            existing.key_hash = key_hash
            existing.is_active = True
        else:
            api_key = APIKey(name=name, key_hash=key_hash, role="admin")
            session.add(api_key)

        await session.commit()

    # Save to file
    save_admin_key(raw_key)
    await engine.dispose()
    return raw_key


def main():
    parser = argparse.ArgumentParser(description="WRD API Initialization")
    parser.add_argument("--create-admin", action="store_true", help="Create admin API key")
    parser.add_argument("--non-interactive", action="store_true", help="Skip confirmation prompts")
    parser.add_argument("--admin-name", default="admin", help="Name for the admin key")
    parser.add_argument("--skip-migrations", action="store_true", help="Skip DB migrations")
    args = parser.parse_args()

    console.print(Panel.fit(
        "[bold cyan]WRD API v2.0.0 — Initialization[/bold cyan]",
        border_style="cyan",
    ))

    async def run():
        # Run migrations unless skipped
        if not args.skip_migrations:
            ok = await _run_migrations()
            if not ok:
                sys.exit(1)

        # Create admin key
        if args.create_admin:
            if not args.non_interactive:
                confirm = input("\nCreate admin API key? [y/N] ").strip().lower()
                if confirm != "y":
                    console.print("[yellow]Skipped admin key creation[/yellow]")
                    return

            console.print(f"[blue]→[/blue] Creating admin key '{args.admin_name}'...")
            raw_key = await _create_admin_key(args.admin_name)

            table = Table(title="Admin API Key", show_header=True)
            table.add_column("Field", style="cyan")
            table.add_column("Value", style="green")
            table.add_row("Key Name", args.admin_name)
            table.add_row("API Key", raw_key)
            table.add_row("Saved to", os.environ.get("ADMIN_KEY_FILE", "/data/admin_key.txt"))
            table.add_row("Role", "admin")
            console.print(table)

            console.print(Panel(
                "[bold yellow]⚠  Store this key securely. It will not be shown again.[/bold yellow]\n\n"
                f"[dim]Use it with:[/dim]\n"
                f"  curl -H 'Authorization: Bearer {raw_key}' http://localhost:8000/api/v1/clusters",
                border_style="yellow",
            ))

    asyncio.run(run())


if __name__ == "__main__":
    main()
