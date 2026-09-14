# Deployment status

Updated: 2026-09-14.

**Overall: REQUIRES MANUAL AWS STEP.** A public working demo is not yet verified, and no Live Demo URL has been added to README.

| Status | Evidence |
|---|---|
| READY | Production Compose, persistent SQLite, Caddy HTTPS, Nginx WebSocket proxy, secure cookies, same-origin API URLs, deployment scripts, and beginner-friendly AWS guide are implemented. |
| VERIFIED | Both Docker images built locally and on the actual Lightsail instance. |
| VERIFIED | Local production HTTPS/WSS testing passed Normal Demo and Safety Demo with actual Bedrock-selected Strands tools and database writes. |
| VERIFIED | Normal Demo: 14 route points, 13 distinct WebSocket map updates, 2 real agent invocations, and 14,530 Bedrock tokens. |
| VERIFIED | Safety Demo: 13 route points, 13 distinct WebSocket map updates, 3 real agent invocations, and 29,537 Bedrock tokens. |
| VERIFIED | Secure account registration/login/logout, untrusted-origin rejection, unauthorized route denial, community coordinate redaction, route history, and lost-item retracing. |
| VERIFIED | Account, route points, and agent action records survived container restart. |
| VERIFIED | Frontend typecheck and production build; backend suite includes 21 tests, including inference concurrency and late-action rejection. |
| VERIFIED | Secret scan of versionable files and reachable Git objects found no current credentials or private keys. |
| REQUIRES MANUAL AWS STEP | `dev` is denied `iam:CreateUser` for `trail-live-demo-bedrock`; apply `deploy/operator-iam-policy.json`, supply Bedrock-only runtime credentials, or explicitly authorize use of the existing dev credentials. |
| NOT WORKING | Public application and publicly trusted HTTPS are not started/verified until runtime credentials are configured. |

## AWS resources already created

- Instance: `trail-live-demo`, Ubuntu 24.04, `small_3_0`, `us-west-2a`.
- Static IP: `trail-live-demo-ip`, address `35.160.30.196`.
- Planned hostname: `trail.35-160-30-196.sslip.io`; this is not a verified live-demo link.
- SSH key: `trail-live-demo-key`; private key remains in ignored `.local`.
- Docker is installed and enabled, and both application images have been built on AWS.
- Instance charges apply while this resource exists; the selected bundle is $12/month plus Bedrock usage.

## Remaining verification

Configure runtime credentials, deploy the latest files, verify the public certificate and browser UI, run `scripts/verify_deployment.py` against the public URL, restart the public containers, and run persistence verification.
Only after those checks pass should README receive its Live Demo URL.

Local measured reports are `.local/local-production-verification.json`, `.local/bedrock-report.json`, and `.local/secret-scan.json`; these files are intentionally ignored.
See [AWS_DEPLOYMENT.md](AWS_DEPLOYMENT.md) for deployment, logs, updates, and resource removal.
