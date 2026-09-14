# tools/__init__.py - Strands tools bound to a single authorized session.
import time
from functools import wraps
from strands import tool
from app.core.config import settings
from app.core.concurrency import mutation_lock
from app.core.db import SessionLocal
from sqlalchemy.orm import Session
from app.models import LostItemSearch, TrailSession
from app.ml.engines import lost_item_points
from app.services import safety
from app.services.sessions import route_points


def build_tools(db: Session | None, session: TrailSession, run_id: str = "local-test") -> list:
    """Closures keep model-selected tools scoped to one server-authorized session."""

    supplied_db = db
    session_id, owner_id = session.id, session.user_id
    call_count = 0

    def audited(function):
        """Scope each actual tool execution to fresh state and a short transaction."""
        @wraps(function)
        async def invoke(*args, **kwargs):
            nonlocal db, session, call_count
            call_count += 1
            if call_count > 16:
                raise RuntimeError("Agent tool budget exceeded")

            def perform():
                # Confirm ownership and liveness again after model inference.
                if not session or session.user_id != owner_id or not session.active:
                    raise ValueError("Session is no longer active")
                token = safety.action_origin.set(settings.trail_agent_mode)
                try:
                    output = function(*args, **kwargs)
                    safety.decision(db, session, "TOOL_REJECTED" if output.get("permitted") is False else "TOOL_EXECUTED",
                                    function.__name__ + " executed", metrics={"tool": function.__name__, "output": output, "run_id": run_id})
                    db.flush()
                    return output
                finally:
                    safety.action_origin.reset(token)

            if supplied_db is not None:
                return perform()
            async with mutation_lock:
                with SessionLocal() as current_db:
                    db, session = current_db, current_db.get(TrailSession, session_id)
                    try:
                        output = perform()
                        current_db.commit()
                        return output
                    except Exception:
                        current_db.rollback()
                        raise
        return invoke

    @tool
    @audited
    def get_session_status() -> dict:
        """Read current motion, safety state, and evidence without precise coordinates."""
        return {key: session.state.get(key) for key in ("motion_status", "stop_duration_seconds", "inactivity_seconds", "risk_score", "anomaly_score", "seclusion_score", "source")} | {"safety_state": session.safety_state, "checkin_permitted": safety.checkin_permitted(session, time.time()), "escalation_due": bool(session.checkin_deadline and time.time() >= session.checkin_deadline)}

    @tool
    @audited
    def calculate_route_risk() -> dict:
        """Read the RiskEngine's measured contributions and data provenance."""
        return {"score": session.state.get("risk_score"), "factors": session.state.get("risk_factors"), "source": session.state.get("source")}

    @tool
    @audited
    def detect_motion_anomaly() -> dict:
        """Read robust median/MAD pace and stop evidence from the anomaly detector."""
        return {key: session.state.get(key) for key in ("anomaly_score", "reason", "baseline_speed", "robust_z", "stop_duration_seconds")}

    @tool
    @audited
    def calculate_seclusion_score() -> dict:
        """Read the seclusion estimate; missing data must not be presented as safety."""
        return {"score": session.state.get("seclusion_score"), "source": session.state.get("source")}

    @tool
    @audited
    def get_trusted_contacts() -> dict:
        """Return the number of approved recipients without disclosing contact details."""
        return {"approved_recipient_count": len(safety.approved_contacts(db, session))}

    @tool
    @audited
    def send_safety_checkin(reason: str) -> dict:
        """Ask the runner if they are okay, subject to evidence, cooldown, and state gates.

        Args:
            reason: A short uncertainty-aware explanation of the observed evidence.
        """
        return safety.send_checkin(db, session, reason[:500])

    @tool
    @audited
    def notify_trusted_contacts(reason: str) -> dict:
        """Create in-app alerts only after explicit help or an unanswered check-in expires.

        Args:
            reason: Why an authorized escalation is warranted.
        """
        return safety.notify_contacts(db, session, reason[:500])

    @tool
    @audited
    def find_nearby_verified_helpers() -> dict:
        """Evaluate up to five nearby opted-in helpers without disclosing their identity."""
        return {"eligible_helper_count": len(safety.nearby_helpers(db, session))}

    @tool
    @audited
    def create_community_alert() -> dict:
        """Request an approximate zone only after opt-in, escalation, and risk gates pass."""
        return safety.community_alert(db, session)

    @tool
    @audited
    def recommend_safer_route() -> dict:
        """Offer a labelled simulated alternative only when demo risk is elevated."""
        result = safety.suggest_route(db, session)
        return {"permitted": result.get("permitted", bool(result.get("points"))),
                "explanation": result.get("explanation", result.get("reason")), "source": result.get("source")}

    @tool
    @audited
    def analyze_lost_item_route() -> dict:
        """Count possible search locations without exposing coordinates to the model."""
        suggestions = lost_item_points(route_points(db, session.id))
        db.add(LostItemSearch(session_id=session.id, item="Agent route inspection", suggestions=suggestions))
        return {"suggestion_count": len(suggestions), "limitation": "Probabilistic assistance only"}

    @tool
    @audited
    def log_agent_decision(action: str, explanation: str) -> dict:
        """Record model reasoning separately from tool-confirmed actions.

        Args:
            action: The proposed action or NO_ACTION.
            explanation: An uncertainty-aware explanation without private identifiers.
        """
        label = "NO_ACTION" if action == "NO_ACTION" else "AGENT_NOTE"
        safety.decision(db, session, label, explanation)
        return {"logged": True}

    return [get_session_status, calculate_route_risk, detect_motion_anomaly, calculate_seclusion_score,
            get_trusted_contacts, send_safety_checkin, notify_trusted_contacts, find_nearby_verified_helpers,
            create_community_alert, recommend_safer_route, analyze_lost_item_route, log_agent_decision]
