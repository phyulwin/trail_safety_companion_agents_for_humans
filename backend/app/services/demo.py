# services/demo.py - Reproducible sensor events and isolated demo identities.
import secrets
import time
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.auth import passwords
from app.models import CommunityAlert, CommunityHelper, LocationPoint, TrailSession, TrustedContact, User
from app.schemas import LocationInput
from app.services.safety import close_alerts, event
from app.services.sessions import ingest_location

# This is illustrative Pasadena geometry, not a promise of pedestrian access.
DEMO_ROUTE = [(34.1498, -118.1453), (34.1502, -118.1453), (34.1506, -118.1453),
              (34.1510, -118.1453), (34.1514, -118.1453), (34.1518, -118.1453),
              (34.1522, -118.1453), (34.1526, -118.1453), (34.1530, -118.1453),
              (34.1534, -118.1453), (34.1538, -118.1453), (34.1540, -118.1451)]


def ensure_demo_data(db: Session, owner: User) -> list[str]:
    """Create inaccessible-password sample people and private history for this runner."""
    contacts = []
    for index, name in enumerate(["Alex Morgan", "Jordan Lee", "Sam Rivera", "Casey Chen", "Taylor Brooks", "Morgan Ellis"]):
        email = f"demo-{owner.id[:8]}-{index}@example.com"
        person = db.scalar(select(User).where(User.email == email))
        if not person:
            person = User(email=email, display_name=name, password_hash=passwords.hash(secrets.token_urlsafe(32)), verified=True, community_opt_in=True)
            db.add(person)
            db.flush()
            if index == 0:
                db.add(TrustedContact(user_id=owner.id, contact_id=person.id))
            else:
                db.add(CommunityHelper(user_id=person.id, latitude=34.153 + index * 0.0002, longitude=-118.145 + index * 0.0002, simulated=True))
        if index == 0:
            contacts.append(person.id)
    existing = db.scalar(select(TrailSession).where(TrailSession.user_id == owner.id, TrailSession.active.is_(False)))
    if not existing:
        for days in (1, 3, 6):
            start = time.time() - days * 86400
            history = TrailSession(user_id=owner.id, started_at=start, ended_at=start + 1800, active=False, is_demo=True,
                                   distance=2350 + days * 140, current_status="STOPPED", state={"source": "SIMULATED history"})
            db.add(history)
            db.flush()
            for index, (lat, lon) in enumerate(DEMO_ROUTE + list(reversed(DEMO_ROUTE))):
                db.add(LocationPoint(session_id=history.id, latitude=lat, longitude=lon, speed=0 if index in (5, 12) else 2.8,
                                     timestamp=start + index * 60, marked=index == 5))
    db.flush()
    return contacts


def demo_tick(db: Session, session: TrailSession, now: float) -> bool:
    """Advance one demo sensor step; the real watchdog controls check-in expiry."""
    if not session.demo_scenario or now < session.demo_next_at:
        return False
    step = session.demo_step
    if step < len(DEMO_ROUTE):
        lat, lon = DEMO_ROUTE[step]
        ingest_location(db, session, LocationInput(latitude=lat, longitude=lon, timestamp=session.started_at + step * 16), simulated=True)
    elif step == len(DEMO_ROUTE):
        lat, lon = DEMO_ROUTE[-1]
        stop = 150 if session.demo_scenario == "safety" else 35
        ingest_location(db, session, LocationInput(latitude=lat, longitude=lon, timestamp=session.started_at + (step - 1) * 16 + stop), simulated=True)
        event(db, session, "DEMO_STOP", f"Simulated stationary sensor interval: {stop} seconds.")
    elif session.demo_scenario == "normal" and session.safety_state == "CHECK_IN":
        close_alerts(db, session, "Simulated runner responded I'M OK; the check-in is closed.")
        # Resume movement so a completed normal demo cannot later re-alert on stale stop evidence.
        ingest_location(db, session, LocationInput(latitude=34.1506, longitude=-118.1453,
                         timestamp=session.state["last_sensor_at"] + 180), simulated=True)
        session.demo_scenario = None
        event(db, session, "DEMO_COMPLETE", "Normal demo complete: no contact escalation.")
    elif session.safety_state == "ESCALATED":
        alert = db.scalar(select(CommunityAlert).where(CommunityAlert.session_id == session.id, CommunityAlert.active.is_(True)))
        if alert and alert.eligible_helpers and not alert.accepted_by:
            alert.accepted_by = [alert.eligible_helpers[0]]
            event(db, session, "HELPER_ACCEPTED", "One simulated verified helper is available; exact coordinates remain private.")
        session.demo_scenario = None
        event(db, session, "DEMO_COMPLETE", "Safety demo complete: contact alert and approximate community assistance.")
    elif session.safety_state == "MONITORING" and session.acknowledged_at:
        session.demo_scenario = None
        event(db, session, "DEMO_COMPLETE", "Runner confirmed safety; automated escalation was cancelled.")
    else:
        return False
    session.demo_step += 1
    session.demo_next_at = now + (3 if step >= len(DEMO_ROUTE) else 1.5)
    return True
