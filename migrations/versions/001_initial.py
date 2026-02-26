"""Initial database schema — all WRD API tables."""
from __future__ import annotations

import uuid

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── clusters ──────────────────────────────────────────────
    op.create_table(
        "clusters",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("name", sa.String(255), unique=True, nullable=False),
        sa.Column("topology_type", sa.String(50), nullable=False, server_default="master-worker"),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_clusters_name", "clusters", ["name"])

    # ── cluster_nodes ─────────────────────────────────────────
    op.create_table(
        "cluster_nodes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column(
            "cluster_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("clusters.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("node_id", sa.String(255), nullable=False),
        sa.Column("node_type", sa.String(50), nullable=False, server_default="worker"),
        sa.Column("site", sa.String(100), nullable=True),
        sa.Column("region", sa.String(100), nullable=True),
        sa.Column("api_key_hash", sa.String(255), nullable=False),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sync_status", sa.String(50), nullable=False, server_default="pending"),
        sa.Column("ruleset_version", sa.String(100), nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("cluster_id", "node_id", name="uq_cluster_node"),
    )
    op.create_index("ix_cluster_nodes_node_id", "cluster_nodes", ["node_id"])

    # ── rule_deployments ──────────────────────────────────────
    op.create_table(
        "rule_deployments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column(
            "cluster_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("clusters.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("initiated_by", sa.String(255), nullable=True),
        sa.Column("ruleset_version", sa.String(100), nullable=False),
        sa.Column("rollout_strategy", sa.String(50), nullable=False, server_default="rolling"),
        sa.Column("status", sa.String(50), nullable=False, server_default="in_progress"),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_log", sa.Text, nullable=True),
    )

    # ── deployment_nodes ──────────────────────────────────────
    op.create_table(
        "deployment_nodes",
        sa.Column(
            "deployment_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("rule_deployments.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "node_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("cluster_nodes.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("status", sa.String(50), nullable=False, server_default="pending"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
    )

    # ── api_keys ──────────────────────────────────────────────
    op.create_table(
        "api_keys",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("name", sa.String(255), nullable=False, unique=True),
        sa.Column("key_hash", sa.String(255), nullable=False),
        sa.Column("role", sa.String(50), nullable=False, server_default="reader"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("deployment_nodes")
    op.drop_table("rule_deployments")
    op.drop_table("api_keys")
    op.drop_index("ix_cluster_nodes_node_id", "cluster_nodes")
    op.drop_table("cluster_nodes")
    op.drop_index("ix_clusters_name", "clusters")
    op.drop_table("clusters")
