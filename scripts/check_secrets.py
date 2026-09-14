# check_secrets.py - Scan versionable files and all reachable Git blobs without printing secrets.
import json
from pathlib import Path
import re
import subprocess
import boto3
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]


def check():
    """Detect known local secrets and credential/private-key signatures in Git content."""
    needles = set()
    for name in (".env", ".env.production", ".env.container"):
        for key, value in dotenv_values(ROOT / name).items():
            if value and len(value) >= 20 and key in ("JWT_SECRET", "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN"):
                needles.add(value.encode())
    credentials = boto3.Session().get_credentials()
    if credentials:
        current = credentials.get_frozen_credentials()
        needles.update(value.encode() for value in (current.access_key, current.secret_key, current.token) if value)
    signatures = [rb"(?:AKIA|ASIA)[A-Z0-9]{16}", rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"]
    findings = []

    def inspect(label, content):
        """Report only the affected path or Git object identifier."""
        if any(value in content for value in needles) or any(re.search(pattern, content) for pattern in signatures):
            findings.append(label)

    names = subprocess.check_output(["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"], cwd=ROOT).decode().split("\0")
    for name in names:
        path = ROOT / name
        if name and path.is_file():
            inspect(name, path.read_bytes())
    objects = subprocess.check_output(["git", "rev-list", "--objects", "--all"], cwd=ROOT).decode().splitlines()
    for entry in objects:
        object_id = entry.split(" ", 1)[0]
        if subprocess.check_output(["git", "cat-file", "-t", object_id], cwd=ROOT).strip() == b"blob":
            inspect(entry, subprocess.check_output(["git", "cat-file", "blob", object_id], cwd=ROOT))
    result = {"passed": not findings, "versionable_files": sum(bool(name) for name in names), "git_objects": len(objects), "findings": findings}
    print(json.dumps(result))
    (ROOT / ".local").mkdir(exist_ok=True)
    (ROOT / ".local/secret-scan.json").write_text(json.dumps(result, indent=2))
    if findings:
        raise SystemExit("Secret scan failed; inspect paths privately before packaging or committing.")


if __name__ == "__main__":
    try:
        check()
    except (OSError, subprocess.CalledProcessError) as error:
        raise SystemExit(f"Secret scan could not complete: {type(error).__name__}") from None
