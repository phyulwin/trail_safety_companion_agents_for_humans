# Trail — Run freely. Trail watches your back.

**Track: Good Neighbor Agents**

## Inspiration

A solo walk or run can be a welcome break, but the people who care about us may still worry; a shared dot on a map offers visibility without helping someone decide whether a long stop is ordinary or worth a check-in.

Trail began with a simple idea: make that monitoring work quieter, more thoughtful, and easier to share across a trusted circle without turning community care into surveillance.

## What it does

Trail is a mobile-first safety companion that records a runner's route, calculates movement, and lets explicitly approved contacts follow a session; its autonomous safety agent watches structured evidence and asks the runner whether they are okay when a check-in is warranted.

If the runner asks for help or leaves a check-in unanswered, Trail creates a trusted-contact in-app alert; when community participation and policy conditions are satisfied, it evaluates up to five simulated verified nearby helpers and shares only an approximate area.

Ten days of private route history also let users retrace an outing and inspect possible lost-item search locations based on pauses, turns, slowdowns, and manual bookmarks.

## How we built it

The frontend uses React, TypeScript, Vite, Tailwind CSS, and Leaflet; FastAPI and SQLAlchemy store sessions in SQLite and deliver authorized live updates over WebSockets.

A central Strands `TrailSafetyAgent` receives sanitized JSON and calls twelve custom tools to inspect risk and motion evidence, check in, notify approved contacts, evaluate community helpers, suggest illustrative alternatives, and record decisions; deterministic policy gates remain authoritative regardless of the model's recommendation.

Amazon Bedrock is the real model provider, and a labelled deterministic custom model provider exercises the same installed Strands loop offline; the local judging demo therefore needs no paid API while the actual Bedrock-backed path remains available and has been smoke-tested on synthetic state.

The experimental engines use explainable weighted factors and median/MAD motion statistics; environmental data, route alternatives, and identity verification are explicitly simulated rather than misrepresented as verified real-world safety information.

## Challenges we ran into

The central challenge was translating uncertain observations into measured actions without giving the model unlimited authority; separating check-ins from escalation and putting consent checks inside tools made that boundary visible and testable.

Another challenge was making a laptop demo demonstrate the real system rather than play a scripted animation; simulated sensor events now pass through the same ingestion, persistence, Strands tool execution, deadlines, and live UI used by ordinary sessions.

Privacy also had to hold after a community helper accepted, so helper responses use a strict allowlist and a fixed coarse location cell without a route identifier or exact-coordinate unlock.

## Accomplishments we're proud of

Trail demonstrates a complete sensor-to-action loop with real Strands tool calls, an understandable decision timeline, two timed end-to-end scenarios, and tests covering authorization, consent, expiry, retention, and community redaction.

The normal path matters as much as the dramatic path: the runner confirms they are okay, the agent closes the check-in, and no contact escalation is created.

## What we learned

Useful agent autonomy depends on well-defined tools, reliable state, and explicit authority boundaries; an agent can reduce routine monitoring work while deterministic rules remain responsible for privacy and irreversible escalation decisions.

We also learned to make data provenance part of the product: unavailable environmental data is more honest and useful than an invented reassurance score.

## What's next for Trail

The next phase is native background location, durable scheduling, verified notification delivery, real routing and environmental providers, identity-verification and community-moderation controls, encrypted storage, and a distributed runtime suitable for AgentCore.

The hackathon MVP does not send SMS/email/push, call emergency services, validate real identity documents, or make medical or crime predictions; it provides supplemental safety assistance and is not a replacement for emergency services.

## Why Good Neighbor Agents

Trail does not only help an individual; it creates a permission-based safety network among runners, trusted contacts, and simulated verified community members, allowing a small community to coordinate care while preserving precise location privacy.

## Submission fields to complete

- Public source repository URL and visible MIT license.
- Working demo video, maximum five minutes; the provided narration targets four minutes.
- AWS Builder ID and any optional live deployment URL.
- Optional publicly published AWS Builder Center article; no article or submission has been published automatically.
