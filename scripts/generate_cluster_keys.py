#!/usr/bin/env python3
"""Generate per-node API keys for offline cluster pre-provisioning."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import argparse
from rich.console import Console
from rich.table import Table

from src.core.security import generate_node_key, hash_api_key

console = Console()


def main():
    parser = argparse.ArgumentParser(description="Generate cluster node API keys")
    parser.add_argument("--cluster-name", required=True, help="Cluster name")
    parser.add_argument("--nodes", required=True, help="Comma-separated node IDs")
    parser.add_argument("--output-json", help="Write keys to JSON file (keys shown once only)")
    args = parser.parse_args()

    node_ids = [n.strip() for n in args.nodes.split(",")]
    results = []

    table = Table(title=f"Node Keys for cluster: {args.cluster_name}", show_header=True)
    table.add_column("Node ID", style="cyan")
    table.add_column("API Key", style="green")

    for node_id in node_ids:
        raw_key = generate_node_key(args.cluster_name, node_id)
        key_hash = hash_api_key(raw_key)
        results.append({"node_id": node_id, "api_key": raw_key, "key_hash": key_hash})
        table.add_row(node_id, raw_key)

    console.print(table)
    console.print("\n[yellow]⚠  Keys shown once only. Store securely.[/yellow]")

    if args.output_json:
        with open(args.output_json, "w") as f:
            json.dump(results, f, indent=2)
        os.chmod(args.output_json, 0o600)
        console.print(f"\n[green]✓[/green] Keys written to {args.output_json}")


if __name__ == "__main__":
    main()
