# simulate_run.py - End-to-end checks against a running server and its real background clock.
import argparse
import json
import secrets
import time
import uuid
from pathlib import Path
import httpx


def exercise(base_url: str, scenarios: list[str]) -> dict:
    """Verify timed scenarios, history, lost-item analysis, and unauthorized access."""
    report = {"health": False, "scenarios": {}, "history": False, "lost_items": False, "authorization": False}
    with httpx.Client(base_url=base_url, timeout=30) as client:
        response = client.get("/health")
        response.raise_for_status()
        report["health"] = response.json()["status"] == "ok"
        registration = client.post("/auth/register", json={"email": f"smoke-{uuid.uuid4()}@example.com",
                                   "password": secrets.token_urlsafe(32), "display_name": "Smoke Test Runner"})
        registration.raise_for_status()
        for scenario in scenarios:
            response = client.post("/demo/start", json={"scenario": scenario})
            response.raise_for_status()
            session_id = response.json()["id"]
            seen = set()
            deadline = time.monotonic() + 100
            while time.monotonic() < deadline:
                response = client.get(f"/sessions/{session_id}")
                response.raise_for_status()
                session = response.json()
                seen.add(session["safety_state"])
                if session["demo_scenario"] is None:
                    break
                time.sleep(0.5)
            else:
                raise AssertionError(f"{scenario} demo did not finish")
            assert "CHECK_IN" in seen, f"{scenario}: missing check-in"
            assert not any(decision["action"] == "POLICY_FALLBACK" for decision in session["decisions"]), "Strands unexpectedly fell back"
            assert any(decision["action"] == "ANALYSIS_COMPLETE" for decision in session["decisions"])
            assert session["safety_state"] == ("ESCALATED" if scenario == "safety" else "MONITORING")
            if scenario == "normal":
                assert "ESCALATED" not in seen
            if scenario == "safety":
                preview = client.get(f"/demo/perspectives/{session_id}").json()
                alert = preview["community"][0]
                assert alert["helper_count"] == 5 and alert["accepted_count"] == 1
                assert "points" not in alert and "session_id" not in alert and "runner_name" not in alert
                assert alert["zone_latitude"] != session["points"][-1]["latitude"]
            with httpx.Client(base_url=base_url) as stranger:
                assert stranger.get(f"/sessions/{session_id}").status_code == 401
            report["authorization"] = True
            client.post(f"/sessions/{session_id}/end").raise_for_status()
            report["scenarios"][scenario] = {"passed": True, "states": sorted(seen), "points": len(session["points"]),
                                              "strands_analyses": sum(d["action"] == "ANALYSIS_COMPLETE" for d in session["decisions"])}
            print(f"PASS: {scenario} demo; actual watchdog, Strands tools, and database.", flush=True)
        history = client.get("/sessions/history").json()
        assert len(history) >= 4
        report["history"] = True
        search = client.post("/lost-items/analyze", json={"session_id": history[-1]["id"], "item": "keys"})
        search.raise_for_status()
        assert len(search.json()["suggestions"]) >= 2
        report["lost_items"] = True
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Exercise the complete Trail demo against a running server")
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--scenario", choices=["both", "normal", "safety"], default="both")
    parser.add_argument("--report", default=".local/smoke-report.json")
    args = parser.parse_args()
    try:
        result = exercise(args.url, ["normal", "safety"] if args.scenario == "both" else [args.scenario])
        destination = Path(args.report)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(f"All live checks passed. Report: {destination}")
    except (httpx.HTTPError, AssertionError, OSError) as error:
        raise SystemExit(f"Live verification failed: {error}") from error
