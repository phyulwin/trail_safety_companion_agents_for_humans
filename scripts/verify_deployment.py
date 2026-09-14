# verify_deployment.py - Assert real HTTPS, WebSockets, Bedrock tools, and persisted application outcomes.
import argparse
import json
import os
from pathlib import Path
import secrets
import ssl
import time
import traceback
import uuid
import httpx
import certifi
from websockets.sync.client import connect
from websockets.exceptions import WebSocketException


def verify(args):
    """Drive synthetic inputs through the deployed application without fabricating results."""
    # Use the same public CA bundle as HTTPX; local tests supply their isolated CA.
    tls = ssl.create_default_context(cafile=args.ca_file or certifi.where())
    destination = Path(args.report)
    destination.parent.mkdir(parents=True, exist_ok=True)
    account_file = destination.with_suffix(".account.json")
    report = {"url": args.url, "verified_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "scenarios": {}}
    with httpx.Client(base_url=args.url.rstrip("/") + "/api/", verify=tls, timeout=15) as client:
        health = client.get("health")
        health.raise_for_status()
        assert health.json()["agent_mode"] == "bedrock"
        assert health.json()["public_demo"] is True
        if args.persistence:
            account = json.loads(account_file.read_text())
            client.post("auth/login", json=account).raise_for_status()
            snapshot = client.get("sessions/" + account["session_id"])
            snapshot.raise_for_status()
            assert len(snapshot.json()["points"]) >= 13
            assert any(d["action"] == "CREATE_COMMUNITY_ALERT" for d in snapshot.json()["decisions"])
            report = json.loads(destination.read_text())
            report["persistence_after_restart"] = True
            destination.write_text(json.dumps(report, indent=2))
            print("PASS: account, route, and agent decisions survive container restart.")
            return
        account = {"email": f"verify-{uuid.uuid4()}@example.com", "password": secrets.token_urlsafe(32), "display_name": "Deployment verification"}
        registered = client.post("auth/register", json=account)
        registered.raise_for_status()
        cookie = registered.headers["set-cookie"].lower()
        assert "httponly" in cookie and "secure" in cookie and "samesite=strict" in cookie
        client.post("auth/logout").raise_for_status()
        assert client.get("users/me").status_code == 401
        client.post("auth/login", json=account).raise_for_status()
        report["authentication_secure_cookies"] = True
        assert client.post("demo/start", json={"scenario": "normal"}, headers={"Origin": "https://untrusted.example"}).status_code == 403
        report["cors"] = True
        for scenario in ("normal", "safety"):
            response = client.post("demo/start", json={"scenario": scenario})
            response.raise_for_status()
            session_id = response.json()["id"]
            seen, lengths, marked = set(), set(), False
            websocket_url = args.url.replace("https://", "wss://").rstrip("/") + "/ws/session/" + session_id
            with connect(websocket_url, ssl=tls, origin=args.url, additional_headers={"Cookie": "trail_token=" + client.cookies.get("trail_token")}, open_timeout=20) as socket:
                deadline = time.monotonic() + 180
                while time.monotonic() < deadline:
                    session = json.loads(socket.recv(timeout=10))["data"]
                    seen.add(session["safety_state"])
                    lengths.add(len(session["points"]))
                    assert session["state"].get("agent_status") != "ERROR", session["state"].get("agent_error")
                    if len(session["points"]) >= 4 and not marked:
                        client.post(f"sessions/{session_id}/mark").raise_for_status()
                        marked = True
                    if session["demo_scenario"] is None and session["state"].get("agent_status") == "COMPLETE":
                        break
                else:
                    raise AssertionError(f"{scenario} did not complete within 180 seconds")
            assert "CHECK_IN" in seen and len(lengths) > 3, f"Observed states {seen}; route lengths {lengths}"
            assert not any(d["action"] == "POLICY_FALLBACK" for d in session["decisions"])
            tools = [d for d in session["decisions"] if d["action"] == "TOOL_EXECUTED"]
            analyses = [d for d in session["decisions"] if d["action"] == "ANALYSIS_COMPLETE"]
            assert tools and all(d["mode"] == "bedrock" for d in tools)
            assert analyses and all(d["metrics"]["usage"]["totalTokens"] > 0 for d in analyses)
            assert any(d["metrics"]["tool"] == "send_safety_checkin" and d["metrics"]["output"].get("permitted") for d in tools)
            if scenario == "normal":
                assert "ESCALATED" not in seen and session["safety_state"] == "MONITORING"
            else:
                assert session["safety_state"] == "ESCALATED"
                for name in ("notify_trusted_contacts", "create_community_alert"):
                    assert any(d["metrics"]["tool"] == name and d["metrics"]["output"].get("permitted") for d in tools)
                preview = client.get("demo/perspectives/" + session_id).json()
                zone = preview["community"][0]
                assert zone["helper_count"] == 5 and zone["accepted_count"] >= 1
                assert set(zone) == {"id", "zone_latitude", "zone_longitude", "radius_km", "helper_count", "accepted_count", "active", "description", "created_at"}
                assert zone["zone_latitude"] != session["points"][-1]["latitude"]
                assert zone["zone_longitude"] != session["points"][-1]["longitude"]
                report["community_coordinate_redaction"] = True
                account["session_id"] = session_id
            with httpx.Client(base_url=args.url + "/api/", verify=tls) as stranger:
                assert stranger.get("sessions/" + session_id).status_code == 401
            found = client.post("lost-items/analyze", json={"session_id": session_id, "item": "keys"})
            found.raise_for_status()
            assert len(found.json()["suggestions"]) >= 1
            client.post(f"sessions/{session_id}/end").raise_for_status()
            report["scenarios"][scenario] = {"passed": True, "states": sorted(seen), "route_points": len(session["points"]), "websocket_map_updates": len(lengths),
                "agent_invocations": len(analyses), "tools": sorted(set(d["metrics"]["tool"] for d in tools)), "bedrock_tokens": sum(d["metrics"]["usage"]["totalTokens"] for d in analyses)}
            print("PASS:", scenario, "with actual Bedrock-selected tools, database writes, and WebSocket updates.", flush=True)
        assert len(client.get("sessions/history").json()) >= 5
        report.update(history=True, lost_item_retracing=True, unauthorized_access_blocked=True)
        account_file.write_text(json.dumps(account))
        os.chmod(account_file, 0o600)
        destination.write_text(json.dumps(report, indent=2))
        print("PASS: all deployment checks; report:", destination)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--ca-file", help="Trust the local test CA; public HTTPS uses system trust")
    parser.add_argument("--report", default=".local/deployment-verification.json")
    parser.add_argument("--persistence", action="store_true")
    try:
        verify(parser.parse_args())
    except (httpx.HTTPError, OSError, AssertionError, TimeoutError, WebSocketException) as error:
        raise SystemExit(f"Verification failed at line {traceback.extract_tb(error.__traceback__)[-1].lineno}: {error}") from None
