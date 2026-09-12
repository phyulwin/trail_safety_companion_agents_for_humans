# api/routes.py - Authenticated FastAPI routes for Trail's complete MVP workflow.
import asyncio
import time
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.core.auth import current_user, issue_token, passwords, throttle
from app.core.config import settings
from app.core.db import get_db
from app.models import CommunityAlert, CommunityHelper, LostItemSearch, TrailSession, TrustedContact, User
from app.schemas import CheckinResponse, ContactInput, Credentials, DemoInput, HelperInput, LocationInput, LostItemInput, ProfileUpdate, Register, SessionInput
from app.ml.engines import lost_item_points
from app.services import safety
from app.services.demo import ensure_demo_data
from app.services.sessions import authorized_session, public_alert, public_session, route_points
from app.services.sessions import ingest_location

router = APIRouter()
mutation_lock = asyncio.Lock()


def profile(user: User) -> dict:
    """Never serialize password hashes, token versions, or other users' profiles."""
    return {"id": user.id, "email": user.email, "display_name": user.display_name,
            "emergency_contact": user.emergency_contact, "verified": user.verified,
            "community_opt_in": user.community_opt_in}


def set_auth_cookie(response: Response, user: User) -> None:
    """Store credentials outside JavaScript-accessible browser storage."""
    response.set_cookie("trail_token", issue_token(user), httponly=True, secure=settings.cookie_secure, samesite="strict", max_age=28800)


@router.post("/auth/register", status_code=201, tags=["Authentication"])
async def register(data: Register, request: Request, response: Response, db: Session = Depends(get_db)):
    """Create an account with an Argon2 password hash."""
    throttle(request)
    async with mutation_lock:
        user = User(email=str(data.email).lower(), display_name=data.display_name.strip(), password_hash=passwords.hash(data.password))
        db.add(user)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            raise HTTPException(409, "An account with this email already exists") from None
        set_auth_cookie(response, user)
        return profile(user)


@router.post("/auth/login", tags=["Authentication"])
async def login(data: Credentials, request: Request, response: Response, db: Session = Depends(get_db)):
    """Authenticate without returning the JWT to browser JavaScript."""
    throttle(request)
    user = db.scalar(select(User).where(User.email == str(data.email).lower()))
    if not user or not passwords.verify(data.password, user.password_hash):
        raise HTTPException(401, "Email or password is incorrect")
    set_auth_cookie(response, user)
    return profile(user)


@router.post("/auth/logout", tags=["Authentication"])
async def logout(response: Response, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Invalidate all existing account tokens, including open WebSocket sessions."""
    async with mutation_lock:
        user.token_version += 1
        db.commit()
    response.delete_cookie("trail_token")
    return {"logged_out": True}


@router.get("/users/me", tags=["Profile"])
async def me(user: User = Depends(current_user)):
    """Return the signed-in account profile."""
    return profile(user)


@router.patch("/users/me", tags=["Profile"])
async def update_profile(data: ProfileUpdate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Revoking community participation immediately closes outgoing community alerts."""
    async with mutation_lock:
        for key, value in data.model_dump().items():
            setattr(user, key, value)
        if not user.community_opt_in:
            owned = select(TrailSession.id).where(TrailSession.user_id == user.id)
            for alert in db.scalars(select(CommunityAlert).where(CommunityAlert.session_id.in_(owned))):
                alert.active = False
        db.commit()
    return profile(user)


@router.post("/users/me/verify-demo", tags=["Demo"])
async def verify_demo(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Explicitly simulate identity verification only when demo mode is enabled."""
    if not settings.demo_mode:
        raise HTTPException(403, "Simulated verification is disabled")
    async with mutation_lock:
        user.verified = True
        db.commit()
    return {**profile(user), "verification": "SIMULATED, not a real identity check"}


@router.get("/trusted-contacts", tags=["Trusted contacts"])
async def contacts(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """List the runner's explicitly approved contacts."""
    rows = db.execute(select(TrustedContact, User).join(User, User.id == TrustedContact.contact_id).where(TrustedContact.user_id == user.id))
    return [{"id": contact.id, "user_id": person.id, "display_name": person.display_name, "email": person.email} for contact, person in rows]


@router.post("/trusted-contacts", status_code=201, tags=["Trusted contacts"])
async def add_contact(data: ContactInput, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Approve another account without automatically sharing any Trail."""
    async with mutation_lock:
        person = db.scalar(select(User).where(User.email == str(data.email).lower()))
        if not person or person.id == user.id:
            raise HTTPException(422, "Choose another registered Trail account")
        contact = TrustedContact(user_id=user.id, contact_id=person.id)
        db.add(contact)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            raise HTTPException(409, "This contact is already approved") from None
        return {"id": contact.id, "user_id": person.id, "display_name": person.display_name}


@router.delete("/trusted-contacts/{contact_id}", tags=["Trusted contacts"])
async def remove_contact(contact_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Revocation applies to REST, WebSockets, and future notifications."""
    async with mutation_lock:
        contact = db.get(TrustedContact, contact_id)
        if not contact or contact.user_id != user.id:
            raise HTTPException(404, "Contact not found")
        db.delete(contact)
        db.commit()
    return {"removed": True}


def create_session(db: Session, user: User, data: SessionInput, is_demo: bool = False) -> TrailSession:
    """Enforce a single active Trail and validate selected recipients."""
    if db.scalar(select(TrailSession).where(TrailSession.user_id == user.id, TrailSession.active.is_(True))):
        raise HTTPException(409, "End your current Trail before starting another")
    approved = set(db.scalars(select(TrustedContact.contact_id).where(TrustedContact.user_id == user.id)))
    if not set(data.share_with).issubset(approved):
        raise HTTPException(422, "Choose only approved trusted contacts")
    if data.community_enabled and not user.community_opt_in:
        raise HTTPException(422, "Enable community participation in your profile first")
    session = TrailSession(user_id=user.id, share_with=list(set(data.share_with)), community_enabled=data.community_enabled, is_demo=is_demo)
    db.add(session)
    db.flush()
    safety.event(db, session, "STARTED", "Trail started with explicit sharing permissions.")
    return session


@router.post("/sessions", status_code=201, tags=["Sessions"])
async def start_session(data: SessionInput, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Start a real GPS session; missing environmental data remains unavailable."""
    async with mutation_lock:
        session = create_session(db, user, data)
        db.commit()
        return public_session(db, session)


@router.get("/sessions/history", tags=["Sessions"])
async def history(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Return only the owner's last ten days of routes."""
    sessions = db.scalars(select(TrailSession).where(TrailSession.user_id == user.id, TrailSession.started_at >= time.time() - settings.route_retention_days * 86400).order_by(TrailSession.started_at.desc()))
    return [public_session(db, session, include_route=False) for session in sessions]


@router.get("/sessions/shared", tags=["Trusted contacts"])
async def shared(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """A trusted-contact dashboard reads only currently shared sessions."""
    owners = select(TrustedContact.user_id).where(TrustedContact.contact_id == user.id)
    sessions = db.scalars(select(TrailSession).where(TrailSession.user_id.in_(owners), TrailSession.started_at >= time.time() - settings.route_retention_days * 86400))
    return [public_session(db, session) for session in sessions if user.id in session.share_with]


@router.get("/sessions/{session_id}", tags=["Sessions"])
async def get_session(session_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Read a Trail only as its owner or an explicitly selected approved contact."""
    return public_session(db, authorized_session(db, session_id, user))


@router.patch("/sessions/{session_id}/sharing", tags=["Sessions"])
async def sharing(session_id: str, data: SessionInput, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Update or revoke sharing for a running Trail."""
    async with mutation_lock:
        session = authorized_session(db, session_id, user, True)
        approved = set(db.scalars(select(TrustedContact.contact_id).where(TrustedContact.user_id == user.id)))
        if not set(data.share_with).issubset(approved) or (data.community_enabled and not user.community_opt_in):
            raise HTTPException(422, "Sharing requires approved contacts and community opt-in")
        session.share_with = data.share_with
        session.community_enabled = data.community_enabled
        if not data.community_enabled:
            for alert in db.scalars(select(CommunityAlert).where(CommunityAlert.session_id == session.id)):
                alert.active = False
        safety.event(db, session, "SHARING_UPDATED", "The runner updated session sharing permissions.")
        db.commit()
        return public_session(db, session)


@router.post("/sessions/{session_id}/location", tags=["Sessions"])
async def location(session_id: str, data: LocationInput, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Record validated sensor events; the autonomous worker performs analysis."""
    async with mutation_lock:
        session = authorized_session(db, session_id, user, True)
        if session.is_demo:
            raise HTTPException(409, "Demo sensor events are controlled by the simulator")
        ingest_location(db, session, data)
        db.commit()
        return public_session(db, session)


@router.post("/sessions/{session_id}/end", tags=["Sessions"])
async def end_session(session_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Stop monitoring and close outstanding requests while keeping the route history."""
    async with mutation_lock:
        session = authorized_session(db, session_id, user, True)
        if session.active:
            safety.close_alerts(db, session, "Runner ended this Trail.")
            session.active, session.ended_at, session.demo_scenario = False, time.time(), None
            db.commit()
        return public_session(db, session)


@router.post("/sessions/{session_id}/mark", tags=["History"])
async def mark_location(session_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Let a runner bookmark the last recorded point for later lost-item retracing."""
    async with mutation_lock:
        session = authorized_session(db, session_id, user, True)
        points = route_points(db, session.id)
        if not session.active or not points:
            raise HTTPException(409, "An active Trail with a recorded location is required")
        points[-1].marked = True
        safety.event(db, session, "LOCATION_MARKED", "Runner bookmarked the last recorded location for later retracing.")
        db.commit()
        return public_session(db, session)


@router.post("/sessions/{session_id}/checkin-response", tags=["Safety"])
async def checkin_response(session_id: str, data: CheckinResponse, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Process a human response before any subsequent autonomous action."""
    async with mutation_lock:
        session = authorized_session(db, session_id, user, True)
        if not session.active:
            raise HTTPException(409, "This Trail has ended")
        if data.response == "OK":
            safety.close_alerts(db, session, "Runner confirmed I'M OK; the safety request is closed.")
        else:
            session.safety_state = "HELP_REQUESTED"
            safety.enforce_required_actions(db, session)
        db.commit()
        return public_session(db, session)


@router.post("/sessions/{session_id}/sos", tags=["Safety"])
async def sos(session_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Explicit SOS creates in-app contact alerts and never calls emergency services."""
    return await checkin_response(session_id, CheckinResponse(response="HELP"), user, db)


@router.get("/sessions/{session_id}/risk", tags=["Safety"])
async def risk(session_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Expose explainable risk inputs and data provenance to authorized viewers."""
    session = authorized_session(db, session_id, user)
    return {key: session.state.get(key) for key in ("risk_score", "risk_level", "risk_factors", "seclusion_score", "anomaly_score", "source")}


@router.get("/agent/decisions/{session_id}", tags=["Agent"])
async def agent_decisions(session_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Supply the frontend's auditable agent decision timeline."""
    return public_session(db, authorized_session(db, session_id, user), False)["decisions"]


@router.post("/lost-items/analyze", tags=["History"])
async def lost_item(data: LostItemInput, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Owners can retrace private routes using heuristic search suggestions."""
    async with mutation_lock:
        session = authorized_session(db, data.session_id, user, True)
        suggestions = lost_item_points(route_points(db, session.id))
        search = LostItemSearch(session_id=session.id, item=data.item, suggestions=suggestions)
        db.add(search)
        db.commit()
        return {"id": search.id, "suggestions": suggestions, "disclaimer": "These are possible search locations, not evidence of where your item was lost."}


@router.put("/community/helper", tags=["Community"])
async def helper_profile(data: HelperInput, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Only verified, opted-in users may advertise their availability."""
    if not user.verified or not user.community_opt_in:
        raise HTTPException(403, "Verification and community opt-in are required")
    async with mutation_lock:
        helper = db.scalar(select(CommunityHelper).where(CommunityHelper.user_id == user.id))
        if not helper:
            helper = CommunityHelper(user_id=user.id, **data.model_dump(), simulated=True)
            db.add(helper)
        else:
            for key, value in data.model_dump().items():
                setattr(helper, key, value)
        db.commit()
    return {"available": helper.available, "verification": "SIMULATED"}


@router.get("/community/alerts", tags=["Community"])
async def community_alerts(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """The community API is intentionally unable to serialize exact runner coordinates."""
    if not user.verified or not user.community_opt_in:
        return []
    rows = db.scalars(select(CommunityAlert).where(CommunityAlert.active.is_(True)))
    return [public_alert(alert) for alert in rows if user.id in alert.eligible_helpers and user.id not in alert.dismissed_by]


@router.post("/community/alerts/{alert_id}/{action}", tags=["Community"])
async def respond_community(alert_id: str, action: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Accepting help never unlocks precise location or session access."""
    if action not in ("accept", "dismiss"):
        raise HTTPException(404, "Action not found")
    async with mutation_lock:
        alert = db.get(CommunityAlert, alert_id)
        if not alert or not alert.active or user.id not in alert.eligible_helpers or not user.verified or not user.community_opt_in:
            raise HTTPException(404, "Alert not found")
        if action == "accept" and user.id not in alert.accepted_by:
            alert.accepted_by = [*alert.accepted_by, user.id]
            safety.event(db, db.get(TrailSession, alert.session_id), "HELPER_ACCEPTED", "A verified helper is available; exact location remains private.")
        elif action == "dismiss":
            alert.dismissed_by = list(set([*alert.dismissed_by, user.id]))
        db.commit()
        return public_alert(alert)


@router.post("/demo/seed", tags=["Demo"])
async def seed(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Create sample contacts and historical routes only for the signed-in runner."""
    if not settings.demo_mode:
        raise HTTPException(403, "Demo mode is disabled")
    async with mutation_lock:
        contacts = ensure_demo_data(db, user)
        db.commit()
        return {"seeded": True, "contact_ids": contacts}


@router.post("/demo/start", status_code=201, tags=["Demo"])
async def demo_start(data: DemoInput, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Demo launch explicitly consents to sample contacts and simulated community sharing."""
    if not settings.demo_mode:
        raise HTTPException(403, "Demo mode is disabled")
    async with mutation_lock:
        contacts = ensure_demo_data(db, user)
        user.community_opt_in = True
        session = create_session(db, user, SessionInput(share_with=contacts, community_enabled=True), True)
        session.demo_scenario = data.scenario
        safety.event(db, session, "DEMO", "Simulated sensor and environmental data; real Strands tools, persistence, and in-app alerts.")
        db.commit()
        return public_session(db, session)


@router.get("/demo/perspectives/{session_id}", tags=["Demo"])
async def perspectives(session_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """An owner-only preview lets judges see sample recipients without account impersonation."""
    session = authorized_session(db, session_id, user, True)
    if not session.is_demo or not settings.demo_mode:
        raise HTTPException(404, "Demo not found")
    alerts = list(db.scalars(select(CommunityAlert).where(CommunityAlert.session_id == session.id, CommunityAlert.active.is_(True))))
    return {"contact": public_session(db, session), "community": [public_alert(alert) for alert in alerts], "label": "Simulated recipient preview"}
