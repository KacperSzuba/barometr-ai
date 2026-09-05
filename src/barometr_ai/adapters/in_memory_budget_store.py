"""Licznik budżetu tokenów w pamięci procesu — domyślny, jednoprocesowy."""

import threading
from datetime import date


class InMemoryTokenBudgetStore:
    """Trzyma liczniki w pamięci procesu.

    OGRANICZENIE: stan nie jest współdzielony. Przy `uvicorn --workers N` albo N replikach
    faktyczny limit to N-krotność deklarowanego, a restart zeruje licznik. Do wdrożenia
    wieloprocesowego służy `RedisTokenBudgetStore`.

    Atomowość `add_usage` jest tu zapewniona blokadą, bo FastAPI woła serwisy z puli wątków
    (`asyncio.to_thread`) — bez niej dwa równoległe żądania mogłyby zgubić doliczenie.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._day: date | None = None
        self._total = 0
        self._per_client: dict[str, int] = {}

    def _rollover(self, day: date) -> None:
        """Nowy dzień zeruje liczniki. Wołane wyłącznie pod blokadą."""
        if self._day != day:
            self._day = day
            self._total = 0
            self._per_client.clear()

    def add_usage(self, day: date, client_id: str, tokens: int) -> int:
        with self._lock:
            self._rollover(day)
            self._total += tokens
            self._per_client[client_id] = self._per_client.get(client_id, 0) + tokens
            return self._total

    def release(self, day: date, client_id: str, tokens: int) -> None:
        with self._lock:
            if self._day != day:
                # Doba zmieniła się między doliczeniem a cofnięciem: liczniki i tak są już
                # wyzerowane, więc odejmowanie zrobiłoby z nich wartość ujemną.
                return
            self._total -= tokens
            self._per_client[client_id] = self._per_client.get(client_id, 0) - tokens

    def usage_today(self, day: date) -> int:
        with self._lock:
            self._rollover(day)
            return self._total

    def usage_for_client(self, day: date, client_id: str) -> int:
        with self._lock:
            self._rollover(day)
            return self._per_client.get(client_id, 0)
