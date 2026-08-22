"""Śledzenie kosztów inference, budżetu tokenów i alertów (Wymóg F1 & Ciągłe)."""

import datetime

from barometr_ai.core.exceptions import BudgetExceededError


class CostTrackerService:
    """Zarządza dziennymi i miesięcznymi limitami tokenów oraz kaskadą kosztową."""

    def __init__(self, daily_budget: int = 1_000_000, alert_threshold: float = 0.8) -> None:
        self.daily_budget = daily_budget
        self.alert_threshold = alert_threshold
        self._current_date = datetime.datetime.now(datetime.UTC).date()
        self._tokens_used_today = 0
        self._client_usage: dict[str, int] = {}

    def _reset_if_new_day(self) -> None:
        today = datetime.datetime.now(datetime.UTC).date()
        if today != self._current_date:
            self._current_date = today
            self._tokens_used_today = 0
            self._client_usage.clear()

    def record_usage(self, client_id: str, tokens: int) -> dict[str, float | int | bool]:
        """Rejestruje zużycie tokenów i sprawdza, czy nie przekroczono budżetu."""
        self._reset_if_new_day()

        if self._tokens_used_today + tokens > self.daily_budget:
            raise BudgetExceededError(
                f"Przekroczono dzienny limit tokenów ({self.daily_budget}).",
                details={
                    "used": self._tokens_used_today,
                    "requested": tokens,
                    "budget": self.daily_budget,
                },
            )

        self._tokens_used_today += tokens
        self._client_usage[client_id] = self._client_usage.get(client_id, 0) + tokens

        usage_ratio = self._tokens_used_today / self.daily_budget
        is_alert = usage_ratio >= self.alert_threshold

        return {
            "tokens_today": self._tokens_used_today,
            "daily_budget": self.daily_budget,
            "usage_ratio": round(usage_ratio, 3),
            "alert_active": is_alert,
        }

    @property
    def tokens_today(self) -> int:
        self._reset_if_new_day()
        return self._tokens_used_today