"""Port magazynu zużycia tokenów.

Licznik budżetu jest jedynym stanem, jaki serwis musi utrzymywać między żądaniami, i jedyną
rzeczą, która stoi na drodze do skalowania poziomego. Wydzielenie go za port pozwala trzymać
ten stan poza procesem, nie naruszając bezstanowości samej warstwy inferencyjnej
([ADR 0001](../../../docs/adr/0001-stateless-ai-service.md)): serwis nadal nie sięga do bazy
biznesowej, a magazyn zna wyłącznie liczniki.
"""

from datetime import date
from typing import Protocol


class TokenBudgetStorePort(Protocol):
    """Magazyn dziennych liczników zużycia tokenów.

    Implementacja współdzielona przez procesy **musi** wykonywać `add_usage` atomowo —
    inaczej dwa workery przepuszczą równolegle po żądaniu przy budżecie starczającym na jedno.
    Odczyty (`usage_today`, `usage_for_client`) mogą być nieatomowe: służą do raportowania
    i do wstępnej bramki, która i tak jest doradcza.
    """

    def add_usage(self, day: date, client_id: str, tokens: int) -> int:
        """Dolicza zużycie i zwraca łączną liczbę tokenów wydanych tego dnia.

        Operacja musi być atomowa: zwrócona wartość to stan **po** doliczeniu, na podstawie
        którego wołający rozstrzyga, czy budżet został przekroczony.
        """
        ...

    def release(self, day: date, client_id: str, tokens: int) -> None:
        """Cofa doliczenie, gdy bramka budżetu odrzuciła żądanie po fakcie."""
        ...

    def usage_today(self, day: date) -> int:
        """Łączne zużycie danego dnia."""
        ...

    def usage_for_client(self, day: date, client_id: str) -> int:
        """Zużycie pojedynczego klienta danego dnia — podstawa dashboardu kosztu (F1)."""
        ...
