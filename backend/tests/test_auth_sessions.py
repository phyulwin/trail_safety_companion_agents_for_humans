# tests/test_auth_sessions.py - Authentication, explicit sharing, sensor validation, and revocation.
import secrets
import time
from fastapi.testclient import TestClient
from app.core.auth import passwords
from app.main import app
from app.models import User


def other_account():
    """Create an independent browser identity for access-control assertions."""
    browser = TestClient(app)
    result = browser.post("/auth/register", json={"email": "other@example.com", "password": secrets.token_urlsafe(20), "display_name": "Other"})
    assert result.status_code == 201
    return browser, result.json()


def test_authentication_cookie_hash_and_logout(client, account, db):
    """Passwords are hashed and old JWTs become unusable after logout."""
    user, credentials = account
    stored = db.get(User, user["id"])
    assert stored.password_hash != credentials["password"]
    assert passwords.verify(credentials["password"], stored.password_hash)
    token = client.cookies.get("trail_token")
    assert client.get("/users/me").status_code == 200
    assert client.post("/auth/logout").status_code == 200
    assert client.get("/users/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401
    assert client.post("/auth/login", json=credentials).status_code == 200
    assert client.post("/auth/login", json={**credentials, "password": "wrong-password"}).status_code == 401


def test_sessions_authorization_and_explicit_sharing(client, account):
    """Approval alone does not share routes; contact revocation also closes WebSocket access."""
    other, person = other_account()
    contact = client.post("/trusted-contacts", json={"email": person["email"]}).json()
    response = client.post("/sessions", json={})
    assert response.status_code == 201
    session_id = response.json()["id"]
    assert other.get(f"/sessions/{session_id}").status_code == 404
    assert other.get(f"/agent/decisions/{session_id}").status_code == 404
    assert client.patch(f"/sessions/{session_id}/sharing", json={"share_with": [person["id"]]}).status_code == 200
    assert other.get(f"/sessions/{session_id}").status_code == 200
    assert len(other.get("/sessions/shared").json()) == 1
    assert other.post(f"/sessions/{session_id}/sos").status_code == 404
    assert other.post("/lost-items/analyze", json={"session_id": session_id}).status_code == 404
    with other.websocket_connect(f"/ws/session/{session_id}") as websocket:
        assert websocket.receive_json()["data"]["id"] == session_id
        client.delete(f"/trusted-contacts/{contact['id']}")
        message = websocket.receive()
        assert message["type"] == "websocket.close" and message["code"] == 4403
    assert other.get(f"/sessions/{session_id}").status_code == 404


def test_location_ingestion_and_validation(client, account):
    """Calculate motion from coordinates, rejecting replay, teleports, and invalid values."""
    route = client.post("/sessions", json={}).json()
    base = time.time()
    point = {"latitude": 34.15, "longitude": -118.145, "timestamp": base}
    assert client.post(f"/sessions/{route['id']}/location", json=point).status_code == 200
    response = client.post(f"/sessions/{route['id']}/location", json={**point, "latitude": 34.1504, "timestamp": base + 16})
    assert response.status_code == 200
    body = response.json()
    assert body["current_status"] == "RUNNING" and 40 < body["distance"] < 50
    assert body["state"]["risk_score"] is None
    assert client.post(f"/sessions/{route['id']}/location", json=point).status_code == 409
    assert client.post(f"/sessions/{route['id']}/location", json={**point, "latitude": 36, "timestamp": base + 32}).status_code == 422
    assert client.post(f"/sessions/{route['id']}/location", json={**point, "latitude": 95}).status_code == 422
    assert client.post("/sessions", json={}).status_code == 409
    assert client.post(f"/sessions/{route['id']}/end").status_code == 200
    assert client.post(f"/sessions/{route['id']}/location", json={**point, "timestamp": base + 45}).status_code == 409


def test_cross_origin_mutation_and_unauthenticated_access(client):
    """Reject browser CSRF and unauthenticated requests before touching session data."""
    assert client.get("/sessions/history").status_code == 401
    assert client.post("/auth/login", json={}, headers={"Origin": "https://untrusted.example"}).status_code == 403


def test_health_and_openapi(client):
    """Ensure all expected API documentation is actually registered."""
    assert client.get("/health").json()["status"] == "ok"
    paths = client.get("/openapi.json").json()["paths"]
    assert "/sessions/{session_id}/location" in paths and "/auth/register" in paths
