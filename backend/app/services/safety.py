# services/safety.py - Deterministic authorization gates for every agent side effect.
import math
import time
from contextvars import ContextVar
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.config import settings
from app.models import AgentDecision, CommunityAlert, CommunityHelper, SafetyEvent, TrailSession, TrustedContact, User
from app.ml.engines import distance_m, safer_route

# Only actual Strands tool execution changes this origin to the configured provider.
action_origin: ContextVar[str] = ContextVar("trail_action_origin", default="policy")


def event(db: Session, session: TrailSession, kind: str, description: str, severity: str = "info", recipients: list | None = None) -> None:
    """Append an auditable action without embedding precise coordinates in text."""
    db.add(SafetyEvent(session_id=session.id, event_type=kind, description=description, severity=severity, recipients=recipients or []))


def decision(db: Session, session: TrailSession, action: str, explanation: str, mode: str | None = None, metrics: dict | None = None) -> None:
    """Persist a sanitized state that has no names, coordinates, or contact details."""
    state = {key: session.state.get(key) for key in ("risk_score", "anomaly_score", "seclusion_score", "stop_duration_seconds", "inactivity_seconds", "source")}
    db.add(AgentDecision(session_id=session.id, action=action, explanation=explanation[:1000], input_state=state,
                         mode=mode or action_origin.get(), metrics=metrics or {}))


def approved_contacts(db: Session, session: TrailSession) -> list[str]:
    """Re-evaluate revocation before every notification or read authorization."""
    approved = set(db.scalars(select(TrustedContact.contact_id).where(TrustedContact.user_id == session.user_id)))
    return [contact for contact in session.share_with if contact in approved]


def checkin_permitted(session: TrailSession, now: float) -> bool:
    """Require evidence and suppress duplicate check-ins after acknowledgement."""
    state = session.state
    return session.active and session.safety_state == "MONITORING" and now - session.acknowledged_at > 120 and (
        (state.get("anomaly_score", 0) > 0.75 and state.get("stop_duration_seconds", 0) >= settings.stop_threshold_seconds)
        or state.get("inactivity_seconds", 0) >= 180
        or ((state.get("risk_score") or 0) >= 60 and state.get("stop_duration_seconds", 0) >= 30)
    )


def send_checkin(db: Session, session: TrailSession, reason: str) -> dict:
    """Only open one check-in, using demo timing solely for simulated sessions."""
    if not checkin_permitted(session, time.time()):
        return {"permitted": False, "reason": "Evidence, state, or cooldown policy blocked check-in"}
    timeout = settings.checkin_timeout_seconds if session.is_demo else settings.production_checkin_timeout_seconds
    session.checkin_deadline = time.time() + timeout
    session.safety_state = "CHECK_IN"
    event(db, session, "CHECK_IN", "Trail noticed you've been stopped longer than usual. Are you okay?", "warning")
    decision(db, session, "CHECK_IN", reason)
    return {"permitted": True, "deadline": session.checkin_deadline}


def notify_contacts(db: Session, session: TrailSession, reason: str) -> dict:
    """An LLM cannot bypass runner consent or an expired unanswered check-in."""
    expired = session.safety_state == "CHECK_IN" and session.checkin_deadline is not None and time.time() >= session.checkin_deadline
    requested = session.safety_state == "HELP_REQUESTED"
    if not session.active or not (expired or requested):
        return {"permitted": False, "reason": "Escalation requires explicit help or an expired check-in"}
    recipients = approved_contacts(db, session)
    session.safety_state = "ESCALATED"
    session.checkin_deadline = None
    event(db, session, "CONTACT_ALERT", f"In-app safety alert created for {len(recipients)} approved contact(s). " + ("No contacts are assigned to this Trail." if not recipients else "Open the trusted contact view to see it."), "high", recipients)
    decision(db, session, "NOTIFY_TRUSTED_CONTACT", reason)
    return {"permitted": True, "recipient_count": len(recipients), "delivery": "in-app only"}


def nearby_helpers(db: Session, session: TrailSession) -> list[str]:
    """Evaluate at most five available, verified, opted-in nearby helpers."""
    location = session.state.get("last_location")
    if not location:
        return []
    candidates = db.execute(select(CommunityHelper, User).join(User, CommunityHelper.user_id == User.id).where(
        CommunityHelper.available.is_(True), User.verified.is_(True), User.community_opt_in.is_(True), User.id != session.user_id))
    distances = [(distance_m(tuple(location), (helper.latitude, helper.longitude)), user.id)
                 for helper, user in candidates if session.is_demo or not helper.simulated]
    return [user_id for distance, user_id in sorted(distances) if distance <= settings.community_radius_km * 1000][:5]


def community_alert(db: Session, session: TrailSession) -> dict:
    """Fixed 0.02-degree cells prevent deriving a precise route from repeated alerts."""
    owner = db.get(User, session.user_id)
    if not session.active or session.safety_state != "ESCALATED" or not session.community_enabled or not owner.community_opt_in:
        return {"permitted": False, "reason": "Community consent or escalation policy blocked the request"}
    if (session.state.get("risk_score") or 0) < settings.community_risk_threshold:
        return {"permitted": False, "reason": "Risk is below the community threshold"}
    existing = db.scalar(select(CommunityAlert).where(CommunityAlert.session_id == session.id, CommunityAlert.active.is_(True)))
    if existing:
        return {"permitted": True, "alert_id": existing.id, "duplicate": True}
    location = session.state.get("last_location")
    if not location:
        return {"permitted": False, "reason": "No location is available"}
    eligible = nearby_helpers(db, session)
    zone = [round((math.floor(value / 0.02) + 0.5) * 0.02, 2) for value in location]
    alert = CommunityAlert(session_id=session.id, zone_latitude=zone[0], zone_longitude=zone[1], radius_km=1.6, eligible_helpers=eligible)
    db.add(alert)
    db.flush()
    event(db, session, "COMMUNITY_ALERT", f"Evaluated {len(eligible)} nearby verified helpers; shared only an approximate 1.6 km zone.", "warning")
    decision(db, session, "CREATE_COMMUNITY_ALERT", "Opt-in, escalation, and risk thresholds satisfied; exact location withheld.")
    return {"permitted": True, "alert_id": alert.id, "helper_count": len(eligible)}


def suggest_route(db: Session, session: TrailSession) -> dict:
    """Keep mock route advice inside explicitly simulated sessions."""
    if not session.is_demo or (session.state.get("risk_score") or 0) < 60 or not session.state.get("last_location"):
        return {"permitted": False, "reason": "No verified live routing provider; or risk below threshold"}
    if session.state.get("suggested_route"):
        return session.state["suggested_route"]
    route = safer_route(*session.state["last_location"])
    session.state = {**session.state, "suggested_route": route}
    event(db, session, "SAFER_ROUTE", route["explanation"])
    decision(db, session, "RECOMMEND_SAFER_ROUTE", route["explanation"])
    return route


def close_alerts(db: Session, session: TrailSession, reason: str) -> None:
    """Resolve both check-ins and community requests without deleting the audit."""
    session.safety_state = "MONITORING"
    session.checkin_deadline = None
    session.acknowledged_at = time.time()
    for alert in db.scalars(select(CommunityAlert).where(CommunityAlert.session_id == session.id)):
        alert.active = False
    event(db, session, "RESOLVED", reason)


def respond_to_checkin(db: Session, session: TrailSession, response: str, reason: str = "Runner confirmed I'M OK; the safety request is closed.") -> None:
    """Apply the same response policy to browser and simulated human input."""
    if not session.active or response not in ("OK", "HELP"):
        raise ValueError("An active session and a valid response are required")
    if response == "OK":
        close_alerts(db, session, reason)
    else:
        session.safety_state = "HELP_REQUESTED"
        enforce_required_actions(db, session)


def respond_as_helper(db: Session, alert: CommunityAlert, helper: User, action: str) -> None:
    """Revalidate helper eligibility without unlocking precise coordinates."""
    if not alert.active or helper.id not in alert.eligible_helpers or not helper.verified or not helper.community_opt_in:
        raise ValueError("Helper is not eligible")
    if action == "accept" and helper.id not in alert.accepted_by:
        alert.accepted_by = [*alert.accepted_by, helper.id]
        event(db, db.get(TrailSession, alert.session_id), "HELPER_ACCEPTED", "A verified helper is available; exact location remains private.")
    elif action == "dismiss":
        alert.dismissed_by = list(set([*alert.dismissed_by, helper.id]))
    elif action != "accept":
        raise ValueError("Unknown helper response")


def enforce_required_actions(db: Session, session: TrailSession) -> None:
    """Safety deadlines cannot depend on model availability or optional tool choice."""
    if checkin_permitted(session, time.time()) and session.state.get("anomaly_score", 0) > 0.75:
        send_checkin(db, session, "Policy fallback: prolonged stop or inactivity crossed the check-in threshold.")
    if session.safety_state == "HELP_REQUESTED" or (session.checkin_deadline and time.time() >= session.checkin_deadline):
        notify_contacts(db, session, "Runner requested help or did not respond before the check-in deadline.")
    if session.safety_state == "ESCALATED":
        community_alert(db, session)
