"""Śledzenie kosztów inference, budżetu tokenów i alertów (Wymóg F1 & Ciągłe)."""

import datetime

from barometr_ai.core.exceptions import BudgetExceededError


class CostTrackerService:
    """Zarządza dziennymi limitami tokenów oraz rozliczeniem per klient.

    OGRANICZENIE: licznik żyje w pamięci procesu. Przy `uvicorn --workers N` faktyczny limit
    to N-krotność deklarowanego, a restart zeruje stan. Wdrożenie wielo-workerowe wymaga
    przeniesienia licznika do współdzielonego magazynu (Redis albo backend) — patrz P0-5
    w audycie. Kontrakt metod jest już pod to przygotowany.
    """

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

    def can_afford(self, tokens: int) -> bool:
        """Czy podana liczba tokenów mieści się jeszcze w dzisiejszym budżecie."""
        self._reset_if_new_day()
        return self._tokens_used_today + tokens <= self.daily_budget

    def ensure_capacity(self, tokens: int) -> None:
        """Bramka przed wywołaniem modelu. Orkiestrator top-N woła `can_afford` i zawęża N."""
        if not self.can_afford(tokens):
            raise BudgetExceededError(
                f"Przekroczono dzienny limit tokenów ({self.daily_budget}).",
                details={
                    "used": self._tokens_used_today,
                    "requested": tokens,
                    "budget": self.daily_budget,
                },
            )

    def record_usage(
        self, client_id: str, tokens: int, *, enforce: bool = True
    ) -> dict[str, float | int | bool]:
        """Rejestruje zużycie tokenów.

        `enforce=False` służy do księgowania tokenów już wydanych u dostawcy: wydatku nie da
        się cofnąć, więc musi trafić do licznika nawet gdy przekracza budżet. Kolejne
        wywołanie zablokuje wtedy `ensure_capacity`.
        """
        self._reset_if_new_day()

        if enforce:
            self.ensure_capacity(tokens)

        self._tokens_used_today += tokens
        self._client_usage[client_id] = self._client_usage.get(client_id, 0) + tokens

        usage_ratio = self._tokens_used_today / self.daily_budget
        return {
            "tokens_today": self._tokens_used_today,
            "daily_budget": self.daily_budget,
            "usage_ratio": round(usage_ratio, 3),
            "alert_active": usage_ratio >= self.alert_threshold,
        }

    def usage_for_client(self, client_id: str) -> int:
        """Zużycie konkretnego klienta — podstawa dashboardu kosztu na klienta z wymogu F1."""
        self._reset_if_new_day()
        return self._client_usage.get(client_id, 0)

    @property
    def tokens_today(self) -> int:
        self._reset_if_new_day()
        return self._tokens_used_today
