# tests/test_engines.py - Explainable experimental engine behavior on controlled inputs.
from types import SimpleNamespace
import pytest
from app.ml.engines import AnomalyDetector, DemoEnvironment, RealEnvironment, RiskEngine, SeclusionEngine, lost_item_points, safer_route


def test_risk_and_seclusion_are_bounded_deterministic():
    """Simulated isolation raises risk, and provenance remains visible."""
    provider = DemoEnvironment()
    low = provider.signals(34.1498, -118.145, 0)
    high = provider.signals(34.154, -118.145, 0)
    engine = RiskEngine()
    assert engine.evaluate(low, 0)["score"] <= 30
    assert 60 < engine.evaluate(high, 150)["score"] <= 100
    assert engine.evaluate(high, 150) == engine.evaluate(high, 150)
    assert 0 <= SeclusionEngine().score(low) < SeclusionEngine().score(high) <= 1
    assert "SIMULATED" in engine.evaluate(high, 150)["source"]
    with pytest.raises(LookupError):
        RealEnvironment().signals(34, -118, 0)


def test_anomaly_normal_short_stop_prolonged_and_inactivity():
    """The statistical model distinguishes sustained stops from a momentary pause."""
    detector = AnomalyDetector()
    assert detector.analyze([2.7, 2.8, 3.1, 2.9], 0)["anomaly_score"] < 0.2
    assert detector.analyze([2.7, 2.8, 3.1, 0], 10)["anomaly_score"] < 0.4
    assert detector.analyze([2.7, 2.8, 3.1, 0], 150)["anomaly_score"] > 0.75
    assert detector.analyze([2.7, 2.8], 0, inactivity=181)["anomaly_score"] > 0.75


def test_lost_item_candidates_and_route_selection():
    """Rank manual marks and slowdowns without claiming a known item location."""
    points = [SimpleNamespace(latitude=34.15 + i * 0.001, longitude=-118.145, speed=speed,
                              timestamp=i * 60, marked=i == 1) for i, speed in enumerate([3, 3, 0, 3])]
    suggestions = lost_item_points(points)
    assert len(suggestions) == 2
    assert any("You marked this location" in point["reasons"] for point in suggestions)
    assert len(safer_route(34.154, -118.145)["safe_points"]) == 2
