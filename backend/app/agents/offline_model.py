# agents/offline_model.py - Explicit local/test-only provider; forbidden in public demos.
import json
from typing import Any, AsyncGenerator
from strands.models import Model


class OfflineSafetyModel(Model):
    """A labelled deterministic model adapter that exercises the actual Strands agent loop."""
    def __init__(self, context: dict):
        """Construct a finite tool plan from engine evidence, not hardcoded demo steps."""
        self.config = {"model_id": "trail-deterministic-demo"}
        self.calls: list[tuple[str, dict]] = [("get_session_status", {}), ("calculate_route_risk", {}),
                                               ("detect_motion_anomaly", {}), ("calculate_seclusion_score", {})]
        if (context.get("risk_score") or 0) >= 60:
            self.calls.append(("recommend_safer_route", {}))
        if context.get("escalation_due"):
            self.calls.extend([("get_trusted_contacts", {}), ("notify_trusted_contacts", {"reason": "Runner requested help or the unanswered check-in expired."}),
                               ("find_nearby_verified_helpers", {}), ("create_community_alert", {})])
        elif context.get("checkin_permitted"):
            self.calls.append(("send_safety_checkin", {"reason": "Unusual stopping behavior combined with the available isolation or inactivity evidence warrants a check-in."}))
        else:
            self.calls.append(("log_agent_decision", {"action": "NO_ACTION", "explanation": "No new intervention is warranted under the current evidence and safety policy."}))
        self.index = 0

    def update_config(self, **model_config: Any) -> None:
        """Implement the SDK model configuration contract."""
        self.config.update(model_config)

    def get_config(self) -> dict:
        """Expose the offline provider identity in Strands traces."""
        return self.config

    async def structured_output(self, output_model, prompt, system_prompt=None, **kwargs):
        """Structured output is unused; this provider exercises native tool calls."""
        raise NotImplementedError("Offline provider supports the tool-calling stream only")
        yield  # pragma: no cover

    async def stream(self, messages, tool_specs=None, system_prompt=None, **kwargs) -> AsyncGenerator[dict, None]:
        """Emit one tool request per turn so actions execute in a predictable order."""
        yield {"messageStart": {"role": "assistant"}}
        if self.index < len(self.calls):
            name, arguments = self.calls[self.index]
            self.index += 1
            yield {"contentBlockStart": {"start": {"toolUse": {"toolUseId": f"trail-{self.index}", "name": name}}}}
            yield {"contentBlockDelta": {"delta": {"toolUse": {"input": json.dumps(arguments)}}}}
            yield {"contentBlockStop": {}}
            yield {"messageStop": {"stopReason": "tool_use"}}
        else:
            yield {"contentBlockStart": {"start": {}}}
            yield {"contentBlockDelta": {"delta": {"text": "Deterministic demo analysis complete; policy-controlled tools executed."}}}
            yield {"contentBlockStop": {}}
            yield {"messageStop": {"stopReason": "end_turn"}}
        yield {"metadata": {"usage": {"inputTokens": 0, "outputTokens": 0, "totalTokens": 0}, "metrics": {"latencyMs": 0}}}

