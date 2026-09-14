# main.py - FastAPI application, autonomous watchdog, and authorized WebSocket snapshots.
import asyncio
import contextlib
import logging
import time
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import select
from app.api.routes import mutation_lock, router
from app.agents.safety_agent import TrailSafetyAgent
from app.core.auth import resolve_token
from app.core.config import settings
from app.core.db import Base, SessionLocal, engine
from app.models import TrailSession
from app.services.demo import demo_tick
from app.services.sessions import authorized_session, cleanup, public_session
from app.services import safety

logger = logging.getLogger("trail")


# Each session has at most one inference task; pending calls never hold SQLite locks.
in_flight: dict[str, asyncio.Task] = {}


async def monitoring_tick() -> None:
    """Advance real sensor processing and schedule bounded, independent agent cycles."""
    for session_id, task in list(in_flight.items()):
        if task.done():
            in_flight.pop(session_id, None)
    async with mutation_lock:
        with SessionLocal() as db:
            sessions = list(db.scalars(select(TrailSession).where(TrailSession.active.is_(True))))
            for session in sessions:
                try:
                    now = time.time()
                    if session.is_demo and now - session.started_at > settings.demo_session_lifetime_seconds:
                        safety.close_alerts(db, session, "Demo time limit reached; route saved in history.")
                        session.active, session.ended_at, session.demo_scenario = False, now, None
                        continue
                    demo_tick(db, session, now)
                    if not session.is_demo:
                        inactivity = now - session.state.get("last_received_at", session.started_at)
                        session.state = {**session.state, "inactivity_seconds": round(inactivity)}
                        if inactivity >= 180:
                            session.state = {**session.state, "anomaly_score": 0.85}
                            session.current_status = "UNKNOWN"
                    expired = bool(session.checkin_deadline and now >= session.checkin_deadline)
                    due = safety.checkin_permitted(session, now) or expired
                    # Completed demonstrations stop spending on repeated Bedrock calls.
                    eligible = not session.is_demo or bool(session.demo_scenario)
                    pending = in_flight.get(session.id)
                    if pending and pending.done():
                        in_flight.pop(session.id, None)
                        pending = None
                    interval = now - session.last_analyzed_at
                    if eligible and not pending and len(in_flight) < settings.max_agent_concurrency and (due or interval >= settings.agent_interval_seconds):
                        if session.state.get("last_location") and (interval >= 5 or not session.last_analyzed_at):
                            session.last_analyzed_at = now
                            task = asyncio.create_task(TrailSafetyAgent().analyze_live(session.id))
                            in_flight[session.id] = task
                except Exception:
                    logger.exception("Monitoring cycle failed for a session")
            db.commit()


async def monitor_loop() -> None:
    """Run one local worker; SQLite deployments must use one Uvicorn worker."""
    last_cleanup = 0.0
    while True:
        try:
            await monitoring_tick()
            if time.time() - last_cleanup >= 60:
                async with mutation_lock:
                    with SessionLocal() as db:
                        cleanup(db)
                last_cleanup = time.time()
        except Exception:
            logger.exception("Watchdog error; retrying next cycle")
        await asyncio.sleep(1)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Create local tables, remove expired data, and cleanly stop the watchdog."""
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        cleanup(db)
    task = asyncio.create_task(monitor_loop())
    try:
        yield
    finally:
        task.cancel()
        for pending in in_flight.values():
            pending.cancel()
        await asyncio.gather(*in_flight.values(), return_exceptions=True)
        in_flight.clear()
        with contextlib.suppress(asyncio.CancelledError):
            await task


app = FastAPI(title="Trail Safety API", version="1.0.0", lifespan=lifespan,
              description="Supplemental safety assistance with policy-controlled Strands tools; notifications are in-app only.")
origins = [origin.strip() for origin in settings.cors_origins.split(",")]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=True,
                   allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"], allow_headers=["Content-Type", "Authorization"])


@app.middleware("http")
async def browser_security(request: Request, call_next):
    """Reject cross-origin cookie mutations and stop sensitive responses being cached."""
    origin = request.headers.get("origin")
    if request.method in ("POST", "PATCH", "PUT", "DELETE") and origin and origin not in origins:
        return JSONResponse({"detail": "Untrusted request origin"}, status_code=403)
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


@app.get("/health", tags=["System"])
async def health():
    """Expose operational mode without secrets or account data."""
    return {"status": "ok", "agent_mode": settings.trail_agent_mode, "demo_mode": settings.demo_mode, "public_demo": settings.public_demo,
            "notification_delivery": "in-app", "identity_verification": "simulated", "environmental_provider": "demo or unavailable"}


app.include_router(router)


@app.websocket("/ws/session/{session_id}")
async def live_session(websocket: WebSocket, session_id: str):
    """Recheck token validity and sharing consent before every precise snapshot."""
    origin = websocket.headers.get("origin")
    if origin and origin not in origins:
        await websocket.close(code=4403)
        return
    token = websocket.cookies.get("trail_token")
    header = websocket.headers.get("authorization", "")
    if header.startswith("Bearer "):
        token = header[7:]
    try:
        with SessionLocal() as db:
            user = resolve_token(token, db)
            authorized_session(db, session_id, user)
        await websocket.accept()
        while True:
            with SessionLocal() as db:
                user = resolve_token(token, db)
                session = authorized_session(db, session_id, user)
                await websocket.send_json({"type": "session", "data": public_session(db, session)})
            await asyncio.sleep(1)
    except HTTPException:
        await websocket.close(code=4403)
    except (WebSocketDisconnect, RuntimeError):
        return
