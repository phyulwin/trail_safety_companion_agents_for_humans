# Trail

**Run freely. Trail watches your back.**

Trail is an AI-powered safety companion for runners, walkers, and joggers. It combines live location sharing, intelligent safety monitoring, trusted contacts, private route history, and a permission-based community network. Trail provides supplemental safety assistance and is not a replacement for emergency services.

## Overview

Going for a run alone should not require constantly sending location updates or asking someone to watch a map. Trail monitors a user's active session and looks for unusual events such as long stops, inactivity, or increased isolation. When something unusual happens, Trail can check whether the runner is okay before deciding whether trusted contacts should be notified.

Important Project Information: 

- [Project Setup Guide](/PROJECT_SETUP.md)

- [Project Features](/PROJECT_FEATURES.md)

- [Trail's Safety Agent](/PROJECT_AGENT.md)

- [AWS Deployment Guide](AWS_DEPLOYMENT.md)

- [Deployment Status](DEPLOYMENT_STATUS.md)

## Features Overview

- Live Trail Tracking
- Trusted Contacts
- AI Safety Monitoring
- Smart Safety Check-Ins
- Community Safety Network
- 10-Day Trail History
- Lost Item Retracing

## Privacy & Security

Location data is highly sensitive, so Trail is designed around explicit permission. Exact runner coordinates and identity are not included in community-helper alerts.

Trail includes:

* Authorized session access
* Explicit trusted contacts
* Password hashing with Argon2
* JWT authentication
* Community participation opt-in
* Approximate community locations
* 10-day route retention
* Agent decision records
* Privacy checks around AI tools

## Current Limitations

Trail is currently an experimental prototype. It does not currently provide real SMS, email, or push notifications, native mobile background tracking, emergency-service dispatch, validated safety predictions, or production identity verification.

The current version uses:

* Foreground browser GPS
* Simulated environmental information
* Simulated identity verification
* Simulated community helpers
* Illustrative safer-route candidates
* In-app notifications

## Future Development

The long-term goal is to make Trail a privacy-focused safety companion that helps people feel more connected when running, walking, or exploring alone.

Future versions of Trail could include:

* Native iOS and Android applications
* Background GPS tracking
* Real push notifications
* Real routing and environmental providers
* Consent-aware identity verification
* Improved anomaly detection
* Encrypted route storage
* Account data export and deletion
* Production monitoring
* Distributed agent execution
* More advanced privacy controls

## AI Usage Acknowledgement

AI tools, including OpenAI Codex, were used to assist with code development, debugging, documentation, and project refinement.

## License

Trail is available under the [MIT License](LICENSE).
