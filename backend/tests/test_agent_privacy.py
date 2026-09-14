# tests/test_agent_privacy.py - Actual Strands execution, safeguards, community privacy, and retention.
import asyncio
import time
from sqlalchemy import func, select
from app.agents.safety_agent import TrailSafetyAgent
from app.core.config import settings
from app.models import AgentDecision, CommunityAlert, LocationPoint, LostItemSearch, SafetyEvent, TrailSession, User
from app.services import safety
from app.services.demo import demo_tick, ensure_demo_data
from app.services.sessions import cleanup, public_alert


def new_session(db, user_id, community=True):
    """Create isolated, stopped evidence independently of the demo script."""
    owner = db.get(User, user_id)
    owner.community_opt_in = community
    contacts = ensure_demo_data(db, owner)
    session = TrailSession(user_id=user_id, is_demo=True, share_with=contacts, community_enabled=community,
                           state={"motion_status": "STOPPED", "risk_score": 85, "seclusion_score": 0.88,
                                  "anomaly_score": 0.9, "stop_duration_seconds": 150, "inactivity_seconds": 0,
                                  "last_location": [34.154, -118.1451], "source": "SIMULATED"})
    db.add(session)
    db.commit()
    return session


def test_actual_strands_checkin_and_escalation(db, account):
    """Verify tool calls pass through the installed Strands loop with no AWS credentials."""
    session = new_session(db, account[0]["id"])
    asyncio.run(TrailSafetyAgent().analyze(db, session))
    assert session.safety_state == "CHECK_IN"
    decisions = list(db.scalars(select(AgentDecision).where(AgentDecision.session_id == session.id)))
    assert not any(d.action == "POLICY_FALLBACK" for d in decisions)
    complete = next(d for d in decisions if d.action == "ANALYSIS_COMPLETE")
    assert complete.metrics["tool_calls"] >= 5
    assert safety.notify_contacts(db, session, "Premature model action")["permitted"] is False
    session.checkin_deadline = time.time() - 1
    asyncio.run(TrailSafetyAgent().analyze(db, session))
    assert session.safety_state == "ESCALATED"
    alert = db.scalar(select(CommunityAlert).where(CommunityAlert.session_id == session.id))
    assert len(alert.eligible_helpers) == 5
    payload = public_alert(alert)
    assert set(payload) == {"id", "zone_latitude", "zone_longitude", "radius_km", "helper_count", "accepted_count", "active", "description", "created_at"}
    assert payload["zone_latitude"] != 34.154 and payload["zone_longitude"] != -118.1451
    assert "session_id" not in payload and "runner_name" not in payload
    safety.enforce_required_actions(db, session)
    assert db.scalar(select(func.count()).select_from(CommunityAlert).where(CommunityAlert.session_id == session.id)) == 1
    assert db.scalar(select(func.count()).select_from(SafetyEvent).where(SafetyEvent.session_id == session.id, SafetyEvent.event_type == "CONTACT_ALERT")) == 1


def test_community_disabled_and_ok_cancels_deadline(db, account):
    """A runner's OK cancels escalation; global and session opt-outs block community alerts."""
    session = new_session(db, account[0]["id"], community=False)
    safety.send_checkin(db, session, "test")
    safety.close_alerts(db, session, "I'm OK")
    safety.enforce_required_actions(db, session)
    assert session.safety_state == "MONITORING" and session.checkin_deadline is None
    assert safety.send_checkin(db, session, "repeat")["permitted"] is False
    session.safety_state = "HELP_REQUESTED"
    safety.enforce_required_actions(db, session)
    assert session.safety_state == "ESCALATED"
    assert db.scalar(select(func.count()).select_from(CommunityAlert)) == 0


def test_agent_normal_motion_does_not_escalate(db, account):
    """A normal jogging state yields a logged NO_ACTION through Strands."""
    session = new_session(db, account[0]["id"])
    session.state = {"motion_status": "RUNNING", "risk_score": 12, "anomaly_score": 0.05, "stop_duration_seconds": 0}
    asyncio.run(TrailSafetyAgent().analyze(db, session))
    assert session.safety_state == "MONITORING"
    assert db.scalar(select(AgentDecision).where(AgentDecision.session_id == session.id, AgentDecision.action == "NO_ACTION"))
    assert db.scalar(select(AgentDecision).where(AgentDecision.session_id == session.id, AgentDecision.action == "POLICY_FALLBACK")) is None


def test_production_timeout_and_model_failure_fallback(db, account, monkeypatch):
    """Model outages cannot disable mandatory check-ins or shorten real-session timeouts."""
    session = new_session(db, account[0]["id"])
    session.is_demo = False
    session.state = {**session.state, "risk_score": None, "seclusion_score": None}
    def fail(*args, **kwargs):
        """Simulate provider initialization failure without any network request."""
        raise RuntimeError("provider unavailable")
    monkeypatch.setattr("app.agents.safety_agent.Agent", fail)
    asyncio.run(TrailSafetyAgent().analyze(db, session))
    assert session.safety_state == "CHECK_IN"
    assert session.checkin_deadline - time.time() > settings.production_checkin_timeout_seconds - 3


def test_10_day_cleanup_cascades_derived_locations(db, account):
    """Expired routes disappear from raw points, audits, risks, and search results."""
    session = new_session(db, account[0]["id"])
    session.started_at = time.time() - 11 * 86400
    db.add(LocationPoint(session_id=session.id, latitude=34, longitude=-118, speed=1, timestamp=session.started_at))
    db.add(LostItemSearch(session_id=session.id, item="keys", suggestions=[{"latitude": 34}]))
    safety.event(db, session, "TEST", "retention")
    safety.community_alert(db, session)
    db.commit()
    assert cleanup(db) == 1
    for model in (LocationPoint, LostItemSearch, SafetyEvent, AgentDecision, CommunityAlert):
        assert db.scalar(select(func.count()).select_from(model).where(model.session_id == session.id)) == 0


def test_automated_normal_and_safety_scenarios(db, account):
    """Feed both complete simulations through the same sensors, agent, and policy pipeline."""
    owner = db.get(User, account[0]["id"])
    owner.community_opt_in = True
    contacts = ensure_demo_data(db, owner)
    for scenario in ("normal", "safety"):
        session = TrailSession(user_id=owner.id, is_demo=True, demo_scenario=scenario, share_with=contacts, community_enabled=True)
        db.add(session)
        db.commit()
        for _ in range(18):
            session.demo_next_at = 0
            tick_time = time.time() + 5 if scenario == "normal" and session.checkin_deadline else time.time()
            changed = demo_tick(db, session, tick_time)
            if changed:
                asyncio.run(TrailSafetyAgent().analyze(db, session))
            if scenario == "safety" and session.checkin_deadline:
                session.checkin_deadline = time.time() - 1
                asyncio.run(TrailSafetyAgent().analyze(db, session))
            db.commit()
            if session.demo_scenario is None:
                break
        assert session.demo_scenario is None
        assert session.safety_state == ("MONITORING" if scenario == "normal" else "ESCALATED")
        if scenario == "normal":
            assert session.current_status == "RUNNING" and session.state["stop_duration_seconds"] == 0
        assert db.scalar(select(AgentDecision).where(AgentDecision.session_id == session.id, AgentDecision.action == "POLICY_FALLBACK")) is None
        if scenario == "safety":
            alert = db.scalar(select(CommunityAlert).where(CommunityAlert.session_id == session.id))
            assert len(alert.accepted_by) == 1


def test_lost_item_api_and_history(client, account):
    """Seeded route analysis is connected to the API and persisted search store."""
    assert client.post("/demo/seed").status_code == 200
    routes = client.get("/sessions/history").json()
    assert len(routes) == 3
    response = client.post("/lost-items/analyze", json={"session_id": routes[0]["id"], "item": "keys"})
    assert response.status_code == 200 and len(response.json()["suggestions"]) >= 2
