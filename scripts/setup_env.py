# setup_env.py - Generate a local signing secret without printing or overwriting secrets.
import secrets
from pathlib import Path


def main() -> None:
    """Copy documented defaults and replace only the blank JWT_SECRET line."""
    root = Path(__file__).resolve().parents[1]
    target = root / ".env"
    if target.exists():
        print(".env already exists; existing configuration preserved.")
        return
    try:
        content = (root / ".env.example").read_text(encoding="utf-8")
        target.write_text(content.replace("JWT_SECRET=\n", f"JWT_SECRET={secrets.token_urlsafe(48)}\n"), encoding="utf-8")
        print("Created .env with a random signing secret; no secret was printed.")
    except OSError as error:
        raise SystemExit(f"Unable to create local configuration: {error}") from error


if __name__ == "__main__":
    main()
