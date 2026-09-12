# core/db.py - SQLite configuration and short-lived SQLAlchemy sessions.
from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from app.core.config import settings


class Base(DeclarativeBase):
    """Shared metadata for Trail's persisted entities."""


engine = create_engine(settings.database_url, connect_args={"check_same_thread": False} if settings.database_url.startswith("sqlite") else {})
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


if settings.database_url.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def configure_sqlite(connection, _record):
        """Enforce cascading deletion and allow readers during short writes."""
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()


def get_db():
    """Rollback incomplete requests and always return connections to the pool."""
    with SessionLocal() as db:
        try:
            yield db
        except Exception:
            db.rollback()
            raise
