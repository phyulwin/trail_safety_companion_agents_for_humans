# models/__init__.py - Relational entities with cascading location retention.
import time
import uuid
from sqlalchemy import Boolean, Float, ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.core.db import Base


def uid() -> str:
    """Use opaque identifiers instead of sequential public identifiers."""
    return str(uuid.uuid4())


class User(Base):
    """An account may be a runner, approved contact, and opted-in helper."""
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(primary_key=True, default=uid)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    password_hash: Mapped[str] = mapped_column(String)
    display_name: Mapped[str] = mapped_column(String(80))
    emergency_contact: Mapped[str] = mapped_column(String(200), default="")
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    community_opt_in: Mapped[bool] = mapped_column(Boolean, default=False)
    token_version: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[float] = mapped_column(Float, default=time.time)


class TrustedContact(Base):
    """Owner approval authorizes a contact; session sharing remains explicit."""
    __tablename__ = "trusted_contacts"
    __table_args__ = (UniqueConstraint("user_id", "contact_id"),)
    id: Mapped[str] = mapped_column(primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    contact_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))


class TrailSession(Base):
    """Store current monitoring state and the runner's sharing consent."""
    __tablename__ = "trail_sessions"
    id: Mapped[str] = mapped_column(primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    started_at: Mapped[float] = mapped_column(Float, default=time.time)
    ended_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    distance: Mapped[float] = mapped_column(Float, default=0)
    current_status: Mapped[str] = mapped_column(String, default="UNKNOWN")
    share_with: Mapped[list] = mapped_column(JSON, default=list)
    community_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    demo_scenario: Mapped[str | None] = mapped_column(String, nullable=True)
    demo_step: Mapped[int] = mapped_column(Integer, default=0)
    demo_next_at: Mapped[float] = mapped_column(Float, default=0)
    state: Mapped[dict] = mapped_column(JSON, default=dict)
    checkin_deadline: Mapped[float | None] = mapped_column(Float, nullable=True)
    safety_state: Mapped[str] = mapped_column(String, default="MONITORING")
    acknowledged_at: Mapped[float] = mapped_column(Float, default=0)
    last_analyzed_at: Mapped[float] = mapped_column(Float, default=0)


class SessionChild:
    """Cascade all session-derived sensitive data when a route expires."""
    id: Mapped[str] = mapped_column(primary_key=True, default=uid)
    session_id: Mapped[str] = mapped_column(ForeignKey("trail_sessions.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[float] = mapped_column(Float, default=time.time)


class LocationPoint(SessionChild, Base):
    """Raw runner coordinates are available only to explicitly authorized viewers."""
    __tablename__ = "location_points"
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    speed: Mapped[float] = mapped_column(Float)
    timestamp: Mapped[float] = mapped_column(Float)
    accuracy: Mapped[float] = mapped_column(Float, default=10)
    marked: Mapped[bool] = mapped_column(Boolean, default=False)


class SafetyEvent(SessionChild, Base):
    """Persist the visible timeline, including the in-app notification outbox."""
    __tablename__ = "safety_events"
    event_type: Mapped[str] = mapped_column(String)
    severity: Mapped[str] = mapped_column(String, default="info")
    description: Mapped[str] = mapped_column(String)
    recipients: Mapped[list] = mapped_column(JSON, default=list)


class AgentDecision(SessionChild, Base):
    """Record executed or rejected decisions with sanitized engine inputs."""
    __tablename__ = "agent_decisions"
    action: Mapped[str] = mapped_column(String)
    explanation: Mapped[str] = mapped_column(String)
    input_state: Mapped[dict] = mapped_column(JSON)
    mode: Mapped[str] = mapped_column(String)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)


class CommunityHelper(Base):
    """Helper discovery uses opt-in locations; verification is explicitly simulated."""
    __tablename__ = "community_helpers"
    id: Mapped[str] = mapped_column(primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    available: Mapped[bool] = mapped_column(Boolean, default=True)
    simulated: Mapped[bool] = mapped_column(Boolean, default=True)


class CommunityAlert(SessionChild, Base):
    """Expose only a fixed coarse cell, never raw route points or runner identity."""
    __tablename__ = "community_alerts"
    zone_latitude: Mapped[float] = mapped_column(Float)
    zone_longitude: Mapped[float] = mapped_column(Float)
    radius_km: Mapped[float] = mapped_column(Float, default=1.5)
    eligible_helpers: Mapped[list] = mapped_column(JSON, default=list)
    accepted_by: Mapped[list] = mapped_column(JSON, default=list)
    dismissed_by: Mapped[list] = mapped_column(JSON, default=list)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class RouteRiskSnapshot(SessionChild, Base):
    """Keep transparent risk factors and data provenance."""
    __tablename__ = "route_risk_snapshots"
    score: Mapped[float] = mapped_column(Float)
    factors: Mapped[dict] = mapped_column(JSON)


class LostItemSearch(SessionChild, Base):
    """Persist heuristic search suggestions without claiming item detection."""
    __tablename__ = "lost_item_searches"
    item: Mapped[str] = mapped_column(String(100), default="")
    suggestions: Mapped[list] = mapped_column(JSON)
