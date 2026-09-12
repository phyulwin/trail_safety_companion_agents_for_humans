# How Trail's AI and ML Work

Trail combines explainable statistical analysis, deterministic safety rules, and an AI agent.

### Route Risk

The experimental Risk Engine evaluates signals including isolation, darkness, road distance, route familiarity, stopping behavior, safe locations, and helper availability.

It produces an experimental score from **0–100**.

Simulated environmental information is always clearly identified and is never presented as real safety data.

### Abnormal Movement Detection

Trail uses median and Median Absolute Deviation (MAD) statistics to identify movement that differs significantly from recent activity.

This can detect events such as prolonged stopping or unexpected inactivity.

These results represent unusual movement evidence and are **not medical predictions**.

### Seclusion Estimation

Trail estimates isolation using signals such as road distance, darkness, familiarity, and simulated environmental information.

The result is a heuristic from **0–1** and does not claim that an area is dangerous.

### Safer Route Suggestions

Trail can compare illustrative route candidates and choose a lower-cost alternative based on its available safety signals.

This feature is experimental and is not a replacement for verified navigation.

## Trail Safety Agent

Trail uses the **Strands Agents SDK** to create `TrailSafetyAgent`.

Instead of functioning as a chatbot, the agent receives structured information from an active Trail and decides which permitted safety tool should be used.

The agent has twelve scoped tools for actions including:

* Reading session status
* Evaluating risk
* Checking movement anomalies
* Calculating seclusion
* Starting check-ins
* Reading trusted contacts
* Sending trusted-contact alerts
* Finding community helpers
* Creating privacy-protected community alerts
* Recommending routes
* Analyzing lost-item routes
* Recording decisions

Agent decisions are stored so users can understand why Trail performed an action.

## Safety Policy

The AI agent does not have unrestricted control.

Trail places deterministic safety and privacy rules around agent actions.

For example:

```text
Location Event
      ↓
Risk / Movement Analysis
      ↓
Trail Safety Agent
      ↓
Safety Policy Check
      ↓
Allowed Action
      ↓
Check-In / Alert / Recommendation
```

Each action checks current permissions and session state before it can run.

This prevents the AI model from bypassing important rules, such as notifying unauthorized contacts or revealing precise coordinates to community members.

## Agent Decision Timeline

Trail records important safety events and AI decisions.

A timeline might look like:

```text
Location update received

↓

Movement anomaly detected
Score: 0.83

↓

Trail Safety Agent
Decision: CHECK_IN

Reason:
Unexpected prolonged stop combined
with increased isolation.

↓

No response

↓

Trusted contacts notified
```

This makes Trail's automated decisions easier to understand.
