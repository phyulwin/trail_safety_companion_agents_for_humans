# ml/engines.py - Deterministic environmental estimates and statistical motion analysis.
import math
from dataclasses import asdict, dataclass
from typing import Protocol
import numpy as np


def distance_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Measure great-circle distance in meters using the haversine formula."""
    lat1, lat2 = math.radians(a[0]), math.radians(b[0])
    dlat, dlon = lat2 - lat1, math.radians(b[1] - a[1])
    value = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 6371000 * 2 * math.asin(min(1, math.sqrt(value)))


@dataclass
class EnvironmentSignals:
    """Normalized inputs include provenance and never represent crime predictions."""
    isolation: float
    darkness: float
    road_distance: float
    unfamiliarity: float
    safe_points: float
    helper_availability: float
    source: str


class EnvironmentProvider(Protocol):
    """Real providers must supply measured inputs and honest provenance."""
    def signals(self, latitude: float, longitude: float, timestamp: float) -> EnvironmentSignals: ...


class DemoEnvironment:
    """A reproducible Pasadena corridor, clearly labelled simulated."""
    def signals(self, latitude: float, longitude: float, timestamp: float) -> EnvironmentSignals:
        """Increase isolation near the demo's northern turnaround."""
        isolation = float(np.clip((latitude - 34.1515) / 0.0025, 0.05, 0.95))
        return EnvironmentSignals(isolation, 0.2 + isolation * 0.65, isolation, isolation * 0.8,
                                  1 - isolation, 0.8, "SIMULATED environmental signals")


class RealEnvironment:
    """An adapter boundary that fails honestly until a real dataset is configured."""
    def signals(self, latitude: float, longitude: float, timestamp: float) -> EnvironmentSignals:
        """Do not invent safety measurements for an unconfigured live route."""
        raise LookupError("No real environmental provider configured; environmental risk is unavailable")


class SeclusionEngine:
    """An interpretable weighted index, not a validated safety classifier."""
    def score(self, signals: EnvironmentSignals) -> float:
        """Combine isolation, road distance, darkness, and unfamiliarity."""
        return round(float(np.clip(signals.isolation * 0.5 + signals.road_distance * 0.25
                                  + signals.darkness * 0.15 + signals.unfamiliarity * 0.1, 0, 1)), 3)


class RiskEngine:
    """Switch providers independently of the decision and privacy policies."""
    def evaluate(self, signals: EnvironmentSignals, stop_seconds: float, deviation: float = 0) -> dict:
        """Return the contribution of each factor alongside a bounded score."""
        factors = {"isolation": signals.isolation * 35, "darkness": signals.darkness * 15,
                   "distance_from_roads": signals.road_distance * 15,
                   "unfamiliarity": signals.unfamiliarity * 10,
                   "stopping": min(stop_seconds / 120, 1) * 15,
                   "fewer_safe_points": (1 - signals.safe_points) * 10,
                   "route_deviation": min(deviation / 150, 1) * 10,
                   "helper_availability": -signals.helper_availability * 5}
        score = int(np.clip(round(sum(factors.values())), 0, 100))
        return {"score": score, "level": "Low" if score <= 30 else "Moderate" if score <= 60 else "Elevated" if score <= 80 else "High",
                "factors": {k: round(v, 2) for k, v in factors.items()}, "source": signals.source,
                "signals": asdict(signals)}


class AnomalyDetector:
    """Use robust median/MAD pace statistics plus explicit inactivity features."""
    def analyze(self, speeds: list[float], stop_seconds: float, inactivity: float = 0, deviation: float = 0) -> dict:
        """Explain the strongest evidence instead of making medical claims."""
        moving = np.array([value for value in speeds[:-1] if value > 0.5], dtype=float)
        baseline = float(np.median(moving)) if moving.size else 2.5
        mad = float(np.median(np.abs(moving - baseline))) if moving.size else 0.4
        latest = speeds[-1] if speeds else baseline
        robust_z = abs(latest - baseline) / max(0.5, 1.4826 * mad)
        stop_feature = min(stop_seconds / 120, 1)
        score = min(1, 0.78 * stop_feature + 0.12 * min(robust_z / 5, 1)
                    + 0.10 * min(deviation / 150, 1))
        score = max(score, min(inactivity / 180, 1) * 0.85)
        reason = "Unexpected prolonged stop" if stop_seconds >= 120 else "Location updates have paused" if inactivity >= 120 else "Motion is within monitoring thresholds"
        return {"anomaly_score": round(score, 3), "reason": reason,
                "severity": "high" if score > 0.75 else "medium" if score > 0.4 else "low",
                "baseline_speed": round(baseline, 2), "robust_z": round(robust_z, 2)}


def safer_route(latitude: float, longitude: float) -> dict:
    """Offer a fixed demo candidate; never imply an unverified path is navigable."""
    candidates = [
        {"name": "Neighborhood streets", "points": [[latitude, longitude], [34.1530, -118.1460], [34.1518, -118.1460], [34.1505, -118.1460], [34.1498, -118.1453]], "cost": 24},
        {"name": "Demo park corridor", "points": [[latitude, longitude], [34.1535, -118.1440], [34.1500, -118.1430]], "cost": 67},
    ]
    selected = min(candidates, key=lambda item: item["cost"])
    return {**selected, "source": "SIMULATED route candidate, not navigation guidance",
            "explanation": "This illustrative alternative favors populated streets and passes two simulated safe points.",
            "safe_points": [{"latitude": 34.1518, "longitude": -118.1460, "label": "Demo public library"},
                            {"latitude": 34.1505, "longitude": -118.1460, "label": "Demo community stop"}]}


def lost_item_points(points: list) -> list[dict]:
    """Rank pauses, pace changes, turns, and manual marks as search candidates."""
    candidates = []
    for index, point in enumerate(points):
        reasons = []
        weight = 0
        previous = points[index - 1] if index else None
        if point.marked:
            reasons.append("You marked this location")
            weight += 5
        if previous and point.speed < 0.5:
            pause = max(0, point.timestamp - previous.timestamp)
            reasons.append(f"Pause of approximately {round(pause)} seconds")
            weight += min(pause / 30, 4)
        if previous and previous.speed - point.speed > 1.5:
            reasons.append("Sharp slowdown")
            weight += 3
        if 0 < index < len(points) - 1:
            following = points[index + 1]
            a = np.array([point.latitude - previous.latitude, point.longitude - previous.longitude])
            b = np.array([following.latitude - point.latitude, following.longitude - point.longitude])
            denominator = float(np.linalg.norm(a) * np.linalg.norm(b))
            if denominator > 0 and float(np.dot(a, b)) / denominator < 0.4:
                reasons.append("Route turn")
                weight += 2
        if reasons:
            candidates.append({"latitude": point.latitude, "longitude": point.longitude,
                               "timestamp": point.timestamp, "reasons": reasons, "weight": round(weight, 2)})
    # Avoid stacking several suggestions on the same small patch of ground.
    selected: list[dict] = []
    for candidate in sorted(candidates, key=lambda item: item["weight"], reverse=True):
        if all(distance_m((candidate["latitude"], candidate["longitude"]), (other["latitude"], other["longitude"])) > 20 for other in selected):
            selected.append(candidate)
        if len(selected) == 5:
            break
    return selected
