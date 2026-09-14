# Real implementation audit

Trail retains the existing FastAPI, React, SQLAlchemy, and SQLite architecture.
The public deployment configuration forces `TRAIL_AGENT_MODE=bedrock`, and `PUBLIC_DEMO=true` refuses a mock provider.

| Capability | Actual implementation | Boundary |
|---|---|---|
| Strands orchestration | Installed `strands.Agent`, `BedrockModel`, twelve registered `@tool` functions, `invoke_async`, sequential tool executor | Offline provider remains explicitly available for isolated local tests only. |
| Model evidence | Sanitized current motion, risk, anomaly, seclusion, consent state, and policy eligibility | No precise coordinates, runner identity, or contact addresses are sent to Bedrock. |
| Real tool execution | Every tool runs against current session state and records its name, sanitized output, provider, and run ID | Session ownership and active state are checked again after inference. |
| Database writes | Check-ins, contact events, community alerts, route suggestions, audit decisions, and lost-item searches persist through SQLAlchemy | Inference runs outside write locks; each live tool owns a short transaction. |
| Judge demos | Server-generated GPS timestamps and positions enter `ingest_location`, then engines, watchdog, Strands, tools, SQLite, and WebSockets | GPS/environment and sample identities/helpers are simulated and labelled. |
| Safety input | Browser and simulated OK/helper responses use shared policy functions | Safety notifications are real persisted in-app events; SMS, email, and emergency dispatch are not integrated. |
| Community privacy | Verified opt-in helpers receive fixed coarse cells through an allowlisted serializer | Acceptance never unlocks precise runner location. |
| History/retracing | Recorded route points and computed pause/turn/mark rankings | Seeded historical routes are labelled examples; illustrative alternative-route geometry is not navigation guidance. |
| Failure behavior | Visible `AGENT_ERROR`, explicit `POLICY_FALLBACK`, and `agent_status=ERROR` | A provider failure never switches to the offline model or claims successful Bedrock inference. |
| Restart behavior | SQLite and certificates live in persistent Docker volumes; watchdog reloads active sessions | Single host and one API worker; no high-availability claim. |

Local production-container verification observed both successful scenarios with actual Bedrock token usage, model-selected side effects, WSS updates, and persistence after restart.
Public deployment readiness is tracked separately in [DEPLOYMENT_STATUS.md](DEPLOYMENT_STATUS.md); local success is not a claim that the public demo is live.
