# services/sessions.py - Authorized session views and sensor processing.
import time
from sqlalchemy import delete, select
from sqlalchemy.orm import Session
from fastapi import HTTPException
from app.core.config import settings
from app.models import AgentDecision, CommunityAlert, LocationPoint, RouteRiskSnapshot, SafetyEvent, TrailSession, User
from app.ml.engines import AnomalyDetector, DemoEnvironment, RealEnvironment, RiskEngine, SeclusionEngine, distance_m
from app.schemas import LocationInput
from app.services.safety import approved_contacts, event


def authorized_session(db: Session, session_id: str, user: User, owner_only: bool = False) -> TrailSession:
    """Use indistinguishable not-found responses for nonexistent and forbidden routes."""
    session = db.get(TrailSession, session_id)
    if not session or session.started_at < time.time() - settings.route_retention_days * 86400:
        raise HTTPException(404, "Trail not found")
    if session.user_id != user.id and (owner_only or user.id not in approved_contacts(db, session)):
        raise HTTPException(404, "Trail not found")
    return session


def route_points(db: Session, session_id: str) -> list[LocationPoint]:
    """Read routes in sensor time order for maps and retracing."""
    return list(db.scalars(select(LocationPoint).where(LocationPoint.session_id == session_id).order_by(LocationPoint.timestamp)))


def ingest_location(db: Session, session: TrailSession, point: LocationInput, simulated: bool = False) -> None:
    """Reject replayed or impossible sensor movement before updating route state."""
    if not session.active:
        raise HTTPException(409, "This Trail has ended")
    points = route_points(db, session.id)
    previous = points[-1] if points else None
    now = time.time()
    if not simulated and (abs(point.timestamp - now) > 120 or point.timestamp < session.started_at - 5):
        raise HTTPException(422, "Location timestamp must be recent and within this Trail")
    if previous and point.timestamp <= previous.timestamp:
        raise HTTPException(409, "Location timestamps must increase")
    delta = point.timestamp - previous.timestamp if previous else 0
    distance = distance_m((previous.latitude, previous.longitude), (point.latitude, point.longitude)) if previous else 0
    speed = distance / delta if delta else 0
    if speed > 15:
        raise HTTPException(422, "Implausible speed; wait for a more accurate GPS reading")
    # Ignore movement smaller than a fraction of GPS uncertainty to reduce jitter.
    if distance < max(2, min(point.accuracy, previous.accuracy if previous else 10) * 0.3):
        speed, distance = 0, 0
    status = "UNKNOWN" if not previous else "RUNNING" if speed >= 2 else "WALKING" if speed >= 0.5 else "STOPPED"
    stop_seconds = session.state.get("stop_duration_seconds", 0) + delta if status == "STOPPED" else 0
    session.distance += distance
    session.current_status = status
    location = LocationPoint(session_id=session.id, **point.model_dump(), speed=speed)
    db.add(location)
    provider = DemoEnvironment() if session.is_demo else RealEnvironment()
    anomaly = AnomalyDetector().analyze([p.speed for p in points[-30:]] + [speed], stop_seconds)
    state = {**session.state, "last_location": [point.latitude, point.longitude], "last_sensor_at": point.timestamp,
             "last_received_at": now, "speed": round(speed, 2), "motion_status": status,
             "stop_duration_seconds": round(stop_seconds), "inactivity_seconds": 0, **anomaly}
    try:
        signals = provider.signals(point.latitude, point.longitude, point.timestamp)
        risk = RiskEngine().evaluate(signals, stop_seconds)
        state.update(risk_score=risk["score"], risk_level=risk["level"], risk_factors=risk["factors"],
                     seclusion_score=SeclusionEngine().score(signals), source=risk["source"])
        db.add(RouteRiskSnapshot(session_id=session.id, score=risk["score"], factors=risk))
    except LookupError as error:
        state.update(risk_score=None, risk_level="Unavailable", risk_factors={}, seclusion_score=None, source=str(error))
    session.state = state
    event(db, session, "LOCATION", f"{status.title()} · {round(speed, 1)} m/s · environmental risk {state['risk_level']}")
    db.flush()


def public_session(db: Session, session: TrailSession, include_route: bool = True) -> dict:
    """This precise serializer is used only after owner/contact authorization."""
    owner = db.get(User, session.user_id)
    events = list(db.scalars(select(SafetyEvent).where(SafetyEvent.session_id == session.id).order_by(SafetyEvent.created_at.desc()).limit(80)))
    decisions = list(db.scalars(select(AgentDecision).where(AgentDecision.session_id == session.id).order_by(AgentDecision.created_at.desc()).limit(120)))
    all_points = route_points(db, session.id)
    points = all_points if include_route else []
    preview = all_points[::max(1, len(all_points) // 24)]
    return {"id": session.id, "user_id": session.user_id, "runner_name": owner.display_name,
            "started_at": session.started_at, "ended_at": session.ended_at, "active": session.active,
            "distance": round(session.distance), "current_status": session.current_status,
            "share_with": approved_contacts(db, session), "community_enabled": session.community_enabled,
            "is_demo": session.is_demo, "demo_scenario": session.demo_scenario, "demo_step": session.demo_step,
            "safety_state": session.safety_state, "checkin_deadline": session.checkin_deadline,
            "state": session.state, "agent_mode": settings.trail_agent_mode,
            "points": [{"latitude": p.latitude, "longitude": p.longitude, "speed": p.speed, "timestamp": p.timestamp, "marked": p.marked} for p in points],
            "route_preview": [[p.latitude, p.longitude] for p in preview],
            "events": [{"id": e.id, "event_type": e.event_type, "description": e.description, "severity": e.severity, "created_at": e.created_at} for e in reversed(events)],
            "decisions": [{"id": d.id, "action": d.action, "explanation": d.explanation, "input_state": d.input_state,
                           "mode": d.mode, "metrics": d.metrics, "created_at": d.created_at} for d in reversed(decisions)]}


def public_alert(alert: CommunityAlert) -> dict:
    """An allowlist prevents identity, session IDs, route points, and exact coordinates leaking."""
    return {"id": alert.id, "zone_latitude": alert.zone_latitude, "zone_longitude": alert.zone_longitude,
            "radius_km": alert.radius_km, "helper_count": len(alert.eligible_helpers),
            "accepted_count": len(alert.accepted_by), "active": alert.active,
            "description": "A Trail user may need assistance within this approximate area.", "created_at": alert.created_at}


def cleanup(db: Session) -> int:
    """Delete entire expired sessions so points, audits, and derived locations cascade."""
    result = db.execute(delete(TrailSession).where(TrailSession.started_at < time.time() - settings.route_retention_days * 86400))
    db.commit()
    return result.rowcount
