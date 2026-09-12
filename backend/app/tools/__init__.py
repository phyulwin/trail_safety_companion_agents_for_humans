# tools/__init__.py - Strands tools bound to a single authorized session.
from strands import tool
from sqlalchemy.orm import Session
from app.models import TrailSession
from app.ml.engines import lost_item_points
from app.services import safety
from app.services.sessions import route_points


def build_tools(db: Session, session: TrailSession) -> list:
    """Closures keep model-selected tools scoped to one server-authorized session."""

    @tool
    def get_session_status() -> dict:
        """Read current motion, safety state, and evidence without precise coordinates."""
        return {key: session.state.get(key) for key in ("motion_status", "stop_duration_seconds", "inactivity_seconds", "risk_score", "anomaly_score", "seclusion_score", "source")} | {"safety_state": session.safety_state}

    @tool
    def calculate_route_risk() -> dict:
        """Read the RiskEngine's measured contributions and data provenance."""
        return {"score": session.state.get("risk_score"), "factors": session.state.get("risk_factors"), "source": session.state.get("source")}

    @tool
    def detect_motion_anomaly() -> dict:
        """Read robust median/MAD pace and stop evidence from the anomaly detector."""
        return {key: session.state.get(key) for key in ("anomaly_score", "reason", "baseline_speed", "robust_z", "stop_duration_seconds")}

    @tool
    def calculate_seclusion_score() -> dict:
        """Read the seclusion estimate; missing data must not be presented as safety."""
        return {"score": session.state.get("seclusion_score"), "source": session.state.get("source")}

    @tool
    def get_trusted_contacts() -> dict:
        """Return the number of approved recipients without disclosing contact details."""
        return {"approved_recipient_count": len(safety.approved_contacts(db, session))}

    @tool
    def send_safety_checkin(reason: str) -> dict:
        """Ask the runner if they are okay, subject to evidence, cooldown, and state gates.

        Args:
            reason: A short uncertainty-aware explanation of the observed evidence.
        """
        return safety.send_checkin(db, session, reason[:500])

    @tool
    def notify_trusted_contacts(reason: str) -> dict:
        """Create in-app alerts only after explicit help or an unanswered check-in expires.

        Args:
            reason: Why an authorized escalation is warranted.
        """
        return safety.notify_contacts(db, session, reason[:500])

    @tool
    def find_nearby_verified_helpers() -> dict:
        """Evaluate up to five nearby opted-in helpers without disclosing their identity."""
        return {"eligible_helper_count": len(safety.nearby_helpers(db, session))}

    @tool
    def create_community_alert() -> dict:
        """Request an approximate zone only after opt-in, escalation, and risk gates pass."""
        return safety.community_alert(db, session)

    @tool
    def recommend_safer_route() -> dict:
        """Offer a labelled simulated alternative only when demo risk is elevated."""
        result = safety.suggest_route(db, session)
        return {"explanation": result.get("explanation", result.get("reason")), "source": result.get("source")}

    @tool
    def analyze_lost_item_route() -> dict:
        """Count possible search locations without exposing coordinates to the model."""
        return {"suggestion_count": len(lost_item_points(route_points(db, session.id))), "limitation": "Probabilistic assistance only"}

    @tool
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
