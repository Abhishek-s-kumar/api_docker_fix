"""WRD API — SQLAlchemy async database models."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Cluster(Base):
    """Registered Wazuh cluster."""

    __tablename__ = "clusters"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), unique=True, nullable=False, index=True)
    topology_type = Column(
        String(50),
        nullable=False,
        default="master-worker",
    )  # single | multi-master | master-worker
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    # Relationships
    nodes = relationship("ClusterNode", back_populates="cluster", cascade="all, delete-orphan")
    deployments = relationship(
        "RuleDeployment", back_populates="cluster", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Cluster {self.name} ({self.topology_type})>"


class ClusterNode(Base):
    """Individual Wazuh manager node within a cluster."""

    __tablename__ = "cluster_nodes"
    __table_args__ = (UniqueConstraint("cluster_id", "node_id", name="uq_cluster_node"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cluster_id = Column(
        UUID(as_uuid=True), ForeignKey("clusters.id", ondelete="CASCADE"), nullable=False
    )
    node_id = Column(String(255), nullable=False, index=True)  # Wazuh node name
    node_type = Column(String(50), nullable=False, default="worker")  # master | worker
    site = Column(String(100), nullable=True)  # Geographic site
    region = Column(String(100), nullable=True)
    api_key_hash = Column(String(255), nullable=False)
    last_seen = Column(DateTime(timezone=True), nullable=True)
    sync_status = Column(String(50), default="pending", nullable=False)
    ruleset_version = Column(String(100), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    # Relationships
    cluster = relationship("Cluster", back_populates="nodes")
    deployment_nodes = relationship("DeploymentNode", back_populates="node")

    def __repr__(self) -> str:
        return f"<ClusterNode {self.node_id} ({self.node_type}) in cluster {self.cluster_id}>"


class RuleDeployment(Base):
    """A rule distribution job across a cluster."""

    __tablename__ = "rule_deployments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cluster_id = Column(
        UUID(as_uuid=True), ForeignKey("clusters.id", ondelete="CASCADE"), nullable=False
    )
    initiated_by = Column(String(255), nullable=True)
    ruleset_version = Column(String(100), nullable=False)
    rollout_strategy = Column(String(50), default="rolling", nullable=False)
    status = Column(String(50), default="in_progress", nullable=False)
    started_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    error_log = Column(Text, nullable=True)

    # Relationships
    cluster = relationship("Cluster", back_populates="deployments")
    deployment_nodes = relationship(
        "DeploymentNode", back_populates="deployment", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<RuleDeployment {self.id} v{self.ruleset_version} {self.status}>"


class DeploymentNode(Base):
    """Per-node status within a deployment job."""

    __tablename__ = "deployment_nodes"

    deployment_id = Column(
        UUID(as_uuid=True),
        ForeignKey("rule_deployments.id", ondelete="CASCADE"),
        primary_key=True,
    )
    node_id = Column(
        UUID(as_uuid=True),
        ForeignKey("cluster_nodes.id", ondelete="CASCADE"),
        primary_key=True,
    )
    status = Column(String(50), default="pending", nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    error_message = Column(Text, nullable=True)

    # Relationships
    deployment = relationship("RuleDeployment", back_populates="deployment_nodes")
    node = relationship("ClusterNode", back_populates="deployment_nodes")


class APIKey(Base):
    """Admin and service API keys."""

    __tablename__ = "api_keys"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False, unique=True)
    key_hash = Column(String(255), nullable=False)
    role = Column(String(50), default="reader", nullable=False)  # admin | writer | reader
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    last_used_at = Column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return f"<APIKey {self.name} ({self.role})>"
