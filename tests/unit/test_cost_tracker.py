"""Testy jednostkowe modułu śledzenia budżetu tokenów i limitów kosztowych."""

import pytest

from barometr_ai.core.exceptions import BudgetExceededError
from barometr_ai.services.cost_tracker_service import CostTrackerService


def test_cost_tracker_under_budget() -> None:
    tracker = CostTrackerService(daily_budget=10_000, alert_threshold=0.8)
    status = tracker.record_usage(client_id="client_1", tokens=2000)

    assert status["tokens_today"] == 2000
    assert status["usage_ratio"] == 0.20
    assert status["alert_active"] is False


def test_cost_tracker_alert_threshold() -> None:
    tracker = CostTrackerService(daily_budget=10_000, alert_threshold=0.8)
    status = tracker.record_usage(client_id="client_1", tokens=8500)

    assert status["tokens_today"] == 8500
    assert status["usage_ratio"] == 0.85
    assert status["alert_active"] is True


def test_cost_tracker_exceeds_budget() -> None:
    tracker = CostTrackerService(daily_budget=1000)

    with pytest.raises(BudgetExceededError):
        tracker.record_usage(client_id="client_1", tokens=1500)