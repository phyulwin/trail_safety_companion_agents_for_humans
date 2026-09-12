# check_bedrock.py - Exercise the real Bedrock-backed Strands path on synthetic, rolled-back state.
import asyncio
import json
import os
import secrets
import sys
import time
from pathlib import Path
from sqlalchemy import select

# Import the app from the repository root without changing its documented database path.
root = Path(__file__).resolve().parents[1]
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
sys.path.insert(0, str(root / "backend"))
from app.agents.safety_agent import TrailSafetyAgent
from app.core.config import settings
from app.core.db import Base, SessionLocal, engine
from app.models import AgentDecision, TrailSession, User


async def main() -> None:
    """Send only synthetic engine state; never print credentials or provider payloads."""
    Base.metadata.create_all(engine)
    settings.trail_agent_mode = "bedrock"
    with SessionLocal() as db:
        try:
            user = User(email=f"bedrock-{secrets.token_hex(8)}@example.com", display_name="Synthetic test", password_hash="unusable-test-hash")
            db.add(user)
            db.flush()
            session = TrailSession(user_id=user.id, is_demo=True, state={"motion_status": "RUNNING", "stop_duration_seconds": 0,
                                   "risk_score": 12, "seclusion_score": 0.1, "anomaly_score": 0.02, "source": "SIMULATED test"})
            db.add(session)
            db.flush()
            started = time.monotonic()
            await TrailSafetyAgent().analyze(db, session)
            decisions = list(db.scalars(select(AgentDecision).where(AgentDecision.session_id == session.id)))
            success = any(decision.action == "ANALYSIS_COMPLETE" for decision in decisions)
            output = {"bedrock_completed": success, "elapsed_seconds": round(time.monotonic() - started, 2),
                      "actions": [decision.action for decision in decisions],
                      "metrics": [decision.metrics for decision in decisions if decision.action == "ANALYSIS_COMPLETE"]}
            target = root / ".local" / "bedrock-report.json"
            target.parent.mkdir(exist_ok=True)
            target.write_text(json.dumps(output, indent=2), encoding="utf-8")
            print(json.dumps(output))
            if not success:
                raise SystemExit("Bedrock check did not complete; review AWS model access and configured timeout.")
        finally:
            # This synthetic connectivity check must not leave extra accounts or routes.
            db.rollback()


if __name__ == "__main__":
    asyncio.run(main())
