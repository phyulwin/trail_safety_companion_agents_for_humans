# seed_demo.py - Create sample data through authenticated HTTP without printing passwords.
import argparse
import secrets
import uuid
import httpx


def seed(base_url: str) -> None:
    """A disposable account isolates seed data from existing real accounts."""
    with httpx.Client(base_url=base_url, timeout=30) as client:
        try:
            response = client.post("/auth/register", json={"email": f"seed-{uuid.uuid4()}@example.com",
                                   "password": secrets.token_urlsafe(32), "display_name": "Demo Runner"})
            response.raise_for_status()
            result = client.post("/demo/seed")
            result.raise_for_status()
            print("Seeded three historical routes, one sample trusted contact, and five simulated helpers.")
            print("For a browser demo, use Run safety demo; it seeds that browser's own account.")
        except httpx.HTTPError as error:
            raise SystemExit(f"Seed failed: {error}") from error


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed Trail through its running API")
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    seed(parser.parse_args().url)
