# tests/test_community_api.py - Verify helper payload privacy through real authenticated endpoints.
import time
from sqlalchemy import select
from app.core.auth import issue_token
from app.models import CommunityAlert, CommunityHelper, TrailSession, User
from app.services import safety
from app.services.demo import ensure_demo_data


def test_helper_acceptance_never_reveals_precise_route(client, account, db):
    """Even an eligible helper who accepts cannot read the runner's route or identity."""
    owner = db.get(User, account[0]["id"])
    owner.community_opt_in = True
    contacts = ensure_demo_data(db, owner)
    session = TrailSession(user_id=owner.id, is_demo=True, community_enabled=True, share_with=contacts,
                           safety_state="HELP_REQUESTED", state={"risk_score": 88, "last_location": [34.154, -118.1451]})
    db.add(session)
    db.flush()
    safety.enforce_required_actions(db, session)
    db.commit()
    alert = db.scalar(select(CommunityAlert).where(CommunityAlert.session_id == session.id))
    helper = db.get(User, alert.eligible_helpers[0])
    headers = {"Authorization": "Bearer " + issue_token(helper)}
    response = client.get("/community/alerts", headers=headers)
    assert response.status_code == 200 and len(response.json()) == 1
    for payload in (response.json()[0], client.post(f"/community/alerts/{alert.id}/accept", headers=headers).json()):
        assert "session_id" not in payload and "user_id" not in payload and "latitude" not in payload
        assert payload["zone_latitude"] != 34.154 and payload["zone_longitude"] != -118.1451
    assert client.get(f"/sessions/{session.id}", headers=headers).status_code == 404
    assert client.get(f"/demo/perspectives/{session.id}", headers=headers).status_code == 404
    assert client.post(f"/community/alerts/{alert.id}/dismiss", headers=headers).status_code == 200
    assert client.get("/community/alerts", headers=headers).json() == []


def test_live_session_excludes_simulated_helpers(client, account, db):
    """Mock identity profiles must never be selected for a real user's GPS emergency."""
    owner = db.get(User, account[0]["id"])
    ensure_demo_data(db, owner)
    session = TrailSession(user_id=owner.id, is_demo=False, state={"last_location": [34.154, -118.1451]})
    db.add(session)
    db.flush()
    assert safety.nearby_helpers(db, session) == []


def test_global_consent_revocation_closes_alerts(client, account, db):
    """Global opt-out invalidates outstanding community requests immediately."""
    owner = db.get(User, account[0]["id"])
    owner.community_opt_in = True
    ensure_demo_data(db, owner)
    session = TrailSession(user_id=owner.id, is_demo=True, community_enabled=True,
                           safety_state="HELP_REQUESTED", state={"risk_score": 88, "last_location": [34.154, -118.1451]})
    db.add(session)
    db.flush()
    safety.enforce_required_actions(db, session)
    db.commit()
    response = client.patch("/users/me", json={"display_name": "Runner", "community_opt_in": False})
    assert response.status_code == 200
    db.expire_all()
    assert not db.scalar(select(CommunityAlert).where(CommunityAlert.session_id == session.id)).active


def test_marking_a_point_is_owner_only(client, account):
    """Manual bookmarks participate in later search without accepting arbitrary coordinates."""
    session = client.post("/sessions", json={}).json()
    assert client.post(f"/sessions/{session['id']}/mark").status_code == 409
    client.post(f"/sessions/{session['id']}/location", json={"latitude": 34.15, "longitude": -118.145, "timestamp": time.time()})
    response = client.post(f"/sessions/{session['id']}/mark")
    assert response.status_code == 200 and response.json()["points"][-1]["marked"]
    search = client.post("/lost-items/analyze", json={"session_id": session["id"], "item": "keys"}).json()
    assert search["suggestions"][0]["reasons"] == ["You marked this location"]
