# Safety and privacy

Trail provides supplemental safety assistance and is not a replacement for emergency services.

## Implemented controls

- Argon2 password hashing; bounded password length; short local login rate window.
- Random environment-provided JWT signing key, issuer and audience validation, eight-hour expiry, HttpOnly/SameSite Strict cookies, and account token revocation on logout.
- Same-origin development proxy, browser Origin checks for mutations, restrictive CORS, and WebSocket Origin validation.
- Owner checks for sensor ingestion, SOS, check-in responses, session sharing, and lost-item analysis; selected trusted contacts receive read-only access.
- Approved-contact removal and session-sharing revocation take effect on subsequent REST and WebSocket reads; community membership never grants route access.
- Fixed 0.02-degree cells with a 1.6 km displayed radius, an allowlisted community response, and no runner identity or session ID in helper payloads.
- Global community opt-in, per-session community consent, simulated verified identity, at most five nearby helper candidates, and risk/escalation gates.
- Acknowledgement cooldown, idempotent escalation and community alerts, explicit OK resolution, server-side deadlines, and deterministic fallbacks.
- Automatic ten-day route retention with database foreign-key cascades for points, risk snapshots, events, decisions, community alerts, and lost-item search results.
- No API keys, signing keys, real identity documents, or plaintext account passwords in tracked files; generated local configuration is ignored by Git.

## What does not happen

The app never calls emergency services, sends SMS/email, performs medical diagnosis, predicts crime, validates a real identity document, or reveals precise locations after a community helper accepts; contact details in a profile do not configure an external notification service.

Simulated environmental conditions remain labelled; real GPS sessions report environmental risk as unavailable until a real provider is configured, while motion and missing-location check-ins remain active.

## Consent and retention details

The demo button expressly enables sample-contact sharing and simulated community participation; ordinary session creation requires the runner to choose approved contacts and enable community participation separately.

The stored route origin determines its retention cutoff, including unusually long-running sessions; account profiles and helper discovery locations are not route history and do not automatically expire under route cleanup.

Deleting database records does not guarantee forensic erasure from disk, backups, SQLite pages, or WAL files; production needs a tested secure-deletion and backup-retention policy, encrypted storage, account deletion, and data export.

## Map provider disclosure

The Leaflet map loads OpenStreetMap tiles over the network, so the tile service can infer the map area and receives ordinary network metadata; it is not provided a Trail identity or a route payload, and strict location privacy would require a self-hosted or appropriately contracted tile service.

The coarse zone reduces precision but is not an anonymity guarantee, especially in sparsely populated areas; no exact-coordinate unlock is implemented in this MVP.

## Production gaps

Browser geolocation works only while the browser permits it and does not provide native background tracking guarantees; phone screen lock, OS suspension, denied permission, loss of connectivity, or server downtime can interrupt monitoring.

Before real-world safety use, add native background location handling, independently tested delivery and acknowledgements, durable scheduling, shared rate limits, real identity verification with abuse controls, verified routing/environmental data, TLS and secure cookies, encrypted storage, and operational incident response.

The current single-process lock and bounded inference can delay concurrent writes; the backend is a hackathon demonstration and has not been load-tested or independently security-audited.
