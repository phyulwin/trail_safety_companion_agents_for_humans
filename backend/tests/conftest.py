# tests/conftest.py - Isolated database and disposable credentials for every test.
import os
import secrets
import tempfile
from pathlib import Path
import pytest

# Set configuration before importing the application; no test touches the demo database.
test_directory = tempfile.TemporaryDirectory(prefix="trail-tests-")
os.environ["DATABASE_URL"] = "sqlite:///" + (Path(test_directory.name) / "tests.db").as_posix()
os.environ["JWT_SECRET"] = secrets.token_urlsafe(48)
os.environ["TRAIL_AGENT_MODE"] = "mock"
os.environ["DEMO_MODE"] = "true"

from fastapi.testclient import TestClient
from app.core.db import Base, SessionLocal, engine
from app.core.auth import attempts
from app.main import app


@pytest.fixture(autouse=True)
def database():
    """Recreate tables without launching the asynchronous watchdog during unit tests."""
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    attempts.clear()
    yield


@pytest.fixture
def client():
    """Allow API and WebSocket tests with manually controlled monitoring ticks."""
    return TestClient(app)


@pytest.fixture
def account(client):
    """Register a fresh user with a generated test-only password."""
    credentials = {"email": "runner@example.com", "password": secrets.token_urlsafe(20), "display_name": "Test Runner"}
    response = client.post("/auth/register", json=credentials)
    assert response.status_code == 201, response.text
    return response.json(), credentials


@pytest.fixture
def db():
    """Provide direct state inspection where policy and retention need controlled time."""
    with SessionLocal() as session:
        yield session


def pytest_sessionfinish(session, exitstatus):
    """Close pooled SQLite handles before Windows removes the test directory."""
    engine.dispose()
    test_directory.cleanup()
