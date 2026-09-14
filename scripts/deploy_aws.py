# deploy_aws.py - Provision and update a persistent Lightsail demo without packaging secrets.
import argparse
import io
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tarfile
import boto3
from botocore.exceptions import ClientError
import httpx
import paramiko
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / ".local"
STATE = LOCAL / "deployment.json"


def save(state):
    """Persist resource identifiers so retries and cleanup target the same resources."""
    LOCAL.mkdir(exist_ok=True)
    STATE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def provision(aws, state):
    """Create one Ubuntu host and a static IP; restrict SSH to the current operator."""
    client = aws.client("lightsail")
    key_path = LOCAL / "trail-deploy.pem"
    if not key_path.exists():
        key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
        key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL, serialization.NoEncryption()))
        os.chmod(key_path, 0o600)
    # Lightsail accepts the OpenSSH public-key text despite the parameter name.
    if not any(item["name"] == state["key_name"] for item in client.get_key_pairs()["keyPairs"]):
        key = serialization.load_pem_private_key(key_path.read_bytes(), password=None)
        public = key.public_key().public_bytes(serialization.Encoding.OpenSSH, serialization.PublicFormat.OpenSSH).decode()
        client.import_key_pair(keyPairName=state["key_name"], publicKeyBase64=public)
    instances = client.get_instances()["instances"]
    if not any(item["name"] == state["instance"] for item in instances):
        client.create_instances(instanceNames=[state["instance"]], availabilityZone=state["region"] + "a",
                                blueprintId="ubuntu_24_04", bundleId="small_3_0", keyPairName=state["key_name"],
                                userData=(ROOT / "deploy/bootstrap.sh").read_text(),
                                tags=[{"key": "Project", "value": "Trail"}])
        print("Lightsail creation requested; rerun provision after the instance reaches running.")
        return
    instance = client.get_instance(instanceName=state["instance"])["instance"]
    if instance["state"]["name"] != "running":
        print("Instance state:", instance["state"]["name"])
        return
    if not any(item["name"] == state["static_ip"] for item in client.get_static_ips()["staticIps"]):
        client.allocate_static_ip(staticIpName=state["static_ip"])
    address = client.get_static_ip(staticIpName=state["static_ip"])["staticIp"]
    if not address.get("isAttached"):
        client.attach_static_ip(staticIpName=state["static_ip"], instanceName=state["instance"])
    state["ip"] = address["ipAddress"]
    state.setdefault("host", "trail." + state["ip"].replace(".", "-") + ".sslip.io")
    admin_ip = httpx.get("https://checkip.amazonaws.com", timeout=15).text.strip()
    client.put_instance_public_ports(instanceName=state["instance"], portInfos=[
        {"fromPort": 80, "toPort": 80, "protocol": "tcp", "cidrs": ["0.0.0.0/0"]},
        {"fromPort": 443, "toPort": 443, "protocol": "tcp", "cidrs": ["0.0.0.0/0"]},
        {"fromPort": 22, "toPort": 22, "protocol": "tcp", "cidrs": [admin_ip + "/32"]}])
    save(state)
    print("Provisioned:", state["instance"], state["ip"], "HTTPS hostname:", state["host"])


def configure_runtime(aws, state):
    """Create a dedicated IAM principal that can only invoke the selected Bedrock model."""
    destination = ROOT / ".env.production"
    if destination.exists():
        print("Preserving existing .env.production; no new access key created.")
        return
    iam = aws.client("iam")
    name = state["instance"] + "-bedrock"
    try:
        iam.create_user(UserName=name, Tags=[{"Key": "Project", "Value": "Trail"}])
    except iam.exceptions.EntityAlreadyExistsException:
        pass
    state["runtime_user"] = name
    save(state)
    account = aws.client("sts").get_caller_identity()["Account"]
    policy = {"Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Action": ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
        "Resource": [f"arn:aws:bedrock:*:{account}:inference-profile/global.anthropic.claude-sonnet-4-6", "arn:aws:bedrock:*::foundation-model/anthropic.claude-sonnet-4-6"]}]}
    iam.put_user_policy(UserName=name, PolicyName="TrailBedrockInvokeOnly", PolicyDocument=json.dumps(policy))
    key = iam.create_access_key(UserName=name)["AccessKey"]
    content = (ROOT / ".env.production.example").read_text()
    content = content.replace("trail.YOUR-STATIC-IP.sslip.io", state["host"]).replace("JWT_SECRET=\n", "JWT_SECRET=" + secrets.token_urlsafe(48) + "\n")
    content = content.replace("AWS_ACCESS_KEY_ID=\n", "AWS_ACCESS_KEY_ID=" + key["AccessKeyId"] + "\n")
    content = content.replace("AWS_SECRET_ACCESS_KEY=\n", "AWS_SECRET_ACCESS_KEY=" + key["SecretAccessKey"] + "\n")
    destination.write_text(content, encoding="utf-8")
    os.chmod(destination, 0o600)
    print("Dedicated Bedrock credentials saved in ignored .env.production; no credentials printed.")


def connect(aws, state):
    """Trust SSH host keys obtained through the authenticated AWS API."""
    details = aws.client("lightsail").get_instance_access_details(instanceName=state["instance"], protocol="ssh")["accessDetails"]
    client = paramiko.SSHClient()
    known_hosts = LOCAL / "known_hosts"
    if known_hosts.exists():
        client.load_host_keys(str(known_hosts))
    if not details.get("hostKeys") and not known_hosts.exists():
        # Lightsail may omit host keys; pin the first key for this newly provisioned IP.
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    for host in details.get("hostKeys", []):
        entry = paramiko.hostkeys.HostKeyEntry.from_line(state["ip"] + " " + host["algorithm"] + " " + host["publicKey"])
        if entry:
            client.get_host_keys().add(state["ip"], entry.key.get_name(), entry.key)
    client.connect(state["ip"], username="ubuntu", key_filename=str(LOCAL / "trail-deploy.pem"), timeout=20, allow_agent=False, look_for_keys=False)
    client.save_host_keys(str(known_hosts))
    return client


def execute(client, command):
    """Stream non-secret operational output and fail on an unsuccessful command."""
    _, stdout, stderr = client.exec_command(command, get_pty=False)
    stdout.channel.set_combine_stderr(True)
    for line in stdout:
        print(line.rstrip(), flush=True)
    status = stdout.channel.recv_exit_status()
    if status:
        raise RuntimeError(f"Remote command exited {status}")


def deploy(aws, state, build_only=False):
    """Upload only versionable project files and transfer credentials separately by SFTP."""
    files = subprocess.check_output(["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"], cwd=ROOT).decode().split("\0")
    archive = LOCAL / "trail-release.tar.gz"
    with tarfile.open(archive, "w:gz") as package:
        for name in files:
            path = ROOT / name
            if name and path.is_file() and not name.startswith((".git/", ".local/")) and name not in (".env", ".env.production", ".env.container") and not name.endswith((".db", ".pem")):
                package.add(path, arcname=name)
    with connect(aws, state) as client:
        with client.open_sftp() as sftp:
            sftp.put(str(ROOT / "deploy/bootstrap.sh"), "/home/ubuntu/trail-bootstrap.sh")
        execute(client, "if ! command -v docker >/dev/null; then sudo sh /home/ubuntu/trail-bootstrap.sh; fi; sudo mkdir -p /opt/trail; sudo chown ubuntu:ubuntu /opt/trail")
        with client.open_sftp() as sftp:
            sftp.put(str(archive), "/opt/trail/release.tar.gz")
            # Opening with restricted permissions before writing prevents a readable secret window.
            if not build_only:
                remote = "/opt/trail/.env.production"
                with sftp.open(remote, "w") as stream:
                    sftp.chmod(remote, 0o600)
                    stream.write((ROOT / ".env.production").read_text())
        command = "docker compose --env-file .env.production.example -f compose.production.yml build" if build_only else "bash deploy/update.sh"
        execute(client, "cd /opt/trail && tar -xzf release.tar.gz && " + command)



def main():
    """Require an explicit operation and keep resource identity stable across retries."""
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["provision", "configure-runtime", "deploy", "build", "status", "remote"])
    parser.add_argument("--profile", default=None)
    parser.add_argument("--region", default="us-west-2")
    parser.add_argument("--host")
    parser.add_argument("--command", help="Non-secret remote command for logs, verification, or maintenance")
    args = parser.parse_args()
    state = json.loads(STATE.read_text()) if STATE.exists() else {"instance": "trail-live-demo", "static_ip": "trail-live-demo-ip", "key_name": "trail-live-demo-key", "region": args.region}
    if args.host:
        state["host"] = args.host
    save(state)
    aws = boto3.Session(profile_name=args.profile, region_name=state["region"])
    if args.action == "remote":
        if not args.command:
            parser.error("remote requires --command")
        with connect(aws, state) as client:
            execute(client, args.command)
    elif args.action == "build":
        deploy(aws, state, build_only=True)
    elif args.action == "status":
        print(json.dumps(state, indent=2))
    else:
        {"provision": provision, "configure-runtime": configure_runtime, "deploy": deploy}[args.action](aws, state)


if __name__ == "__main__":
    try:
        main()
    except (ClientError, OSError, RuntimeError, paramiko.SSHException) as error:
        # AWS error messages do not include secret key material; never dump request objects.
        raise SystemExit(f"Deployment step failed: {error}") from None
