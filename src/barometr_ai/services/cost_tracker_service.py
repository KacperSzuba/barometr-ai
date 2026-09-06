"""Śledzenie kosztów inference, budżetu tokenów i alertów (Wymóg F1 & Ciągłe)."""

import datetime

from barometr_ai.adapters.in_memory_budget_store import InMemoryTokenBudgetStore
from barometr_ai.core.exceptions import BudgetExceededError
from barometr_ai.ports.token_budget import TokenBudgetStorePort


class CostTrackerService:
    """Zarządza dziennymi limitami tokenów oraz rozliczeniem per klient.

    Stan liczników leży za portem `TokenBudgetStorePort`. Domyślny magazyn trzyma je w pamięci
    procesu — wystarczający dla pojedynczego workera, ale przy N procesach dający N-krotność
    deklarowanego limitu. `RedisTokenBudgetStore` czyni licznik współdzielonym i dopiero on
    pozwala skalować serwis poziomo.

    Bramka budżetu jest **domykana po doliczeniu**, nie przed: `record_usage` najpierw dolicza
    atomowo, a dopiero potem sprawdza wynik i w razie przekroczenia cofa zapis. Kolejność
    „sprawdź, potem dolicz" byłaby wyścigiem — dwa procesy odczytałyby ten sam stan sprzed
    zapisu i oba uznałyby, że budżet starcza.
    """

    def __init__(
        self,
        daily_budget: int = 1_000_000,
        alert_threshold: float = 0.8,
        store: TokenBudgetStorePort | None = None,
    ) -> None:
        self.daily_budget = daily_budget
        self.alert_threshold = alert_threshold
        self._store: TokenBudgetStorePort = store or InMemoryTokenBudgetStore()

    @staticmethod
    def _today() -> datetime.date:
        return datetime.datetime.now(datetime.UTC).date()

    def can_afford(self, tokens: int) -> bool:
        """Czy podana liczba tokenów mieści się jeszcze w dzisiejszym budżecie.

        Bramka doradcza: między tym odczytem a doliczeniem inny proces może wydać własne
        tokeny. Twardego limitu pilnuje `record_usage`, które dolicza atomowo.
        """
        return self._store.usage_today(self._today()) + tokens <= self.daily_budget

    def ensure_capacity(self, tokens: int) -> None:
        """Bramka przed wywołaniem modelu. Orkiestrator top-N woła `can_afford` i zawęża N."""
        if not self.can_afford(tokens):
            raise BudgetExceededError(
                f"Przekroczono dzienny limit tokenów ({self.daily_budget}).",
                details={
                    "used": self._store.usage_today(self._today()),
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
        day = self._today()
        total = self._store.add_usage(day, client_id, tokens)

        if enforce and total > self.daily_budget:
            # Zapis cofamy dopiero po stwierdzeniu przekroczenia — do tego momentu inne
            # procesy widzą tokeny jako zajęte, więc nie przepuszczą własnego żądania.
            self._store.release(day, client_id, tokens)
            raise BudgetExceededError(
                f"Przekroczono dzienny limit tokenów ({self.daily_budget}).",
                details={
                    "used": total - tokens,
                    "requested": tokens,
                    "budget": self.daily_budget,
                },
            )

        usage_ratio = total / self.daily_budget
        return {
            "tokens_today": total,
            "daily_budget": self.daily_budget,
            "usage_ratio": round(usage_ratio, 3),
            "alert_active": usage_ratio >= self.alert_threshold,
        }

    def usage_for_client(self, client_id: str) -> int:
        """Zużycie konkretnego klienta — podstawa dashboardu kosztu na klienta z wymogu F1."""
        return self._store.usage_for_client(self._today(), client_id)

    @property
    def tokens_today(self) -> int:
        return self._store.usage_today(self._today())
