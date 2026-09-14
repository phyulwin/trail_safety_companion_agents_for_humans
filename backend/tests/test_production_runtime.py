# test_production_runtime.py - Verify fresh authorization and responsive writes during inference.
import asyncio
from sqlalchemy import select
from app.agents.safety_agent import TrailSafetyAgent
from app.core.concurrency import mutation_lock
from app.core.db import SessionLocal
from app.models import AgentDecision, TrailSession
from app.services.demo import ensure_demo_data
from app.models import User
from app.tools import build_tools


def test_live_agent_uses_short_transactions(db, account, monkeypatch):
    """An API write can acquire the shared lock while Strands awaits its model."""
    owner = db.get(User, account[0]["id"])
    ensure_demo_data(db, owner)
    session = TrailSession(user_id=owner.id, is_demo=True, state={"risk_score": 12, "motion_status": "RUNNING", "stop_duration_seconds": 0})
    db.add(session)
    db.commit()
    entered, release = asyncio.Event(), asyncio.Event()
    from app.agents.offline_model import OfflineSafetyModel
    original = OfflineSafetyModel.stream

    async def paused(self, *args, **kwargs):
        """Hold inference until the simulated concurrent request completes."""
        entered.set()
        await release.wait()
        async for part in original(self, *args, **kwargs):
            yield part

    monkeypatch.setattr(OfflineSafetyModel, "stream", paused)

    async def exercise():
        """Stop the session during inference; late tools must not alter its safety state."""
        task = asyncio.create_task(TrailSafetyAgent().analyze_live(session.id))
        await asyncio.wait_for(entered.wait(), 3)
        await asyncio.wait_for(mutation_lock.acquire(), 1)
        try:
            with SessionLocal() as current:
                row = current.get(TrailSession, session.id)
                row.active = False
                current.commit()
        finally:
            mutation_lock.release()
            release.set()
        await task

    asyncio.run(exercise())
    db.expire_all()
    assert db.get(TrailSession, session.id).safety_state == "MONITORING"
    assert not list(db.scalars(select(AgentDecision).where(AgentDecision.session_id == session.id)))


def test_public_configuration_rejects_mock():
    """Production cannot accidentally start using the deterministic test provider."""
    import pytest
    from pydantic import ValidationError
    from app.core.config import Settings
    with pytest.raises(ValidationError, match="Public demos require"):
        Settings(public_demo=True, trail_agent_mode="mock")
