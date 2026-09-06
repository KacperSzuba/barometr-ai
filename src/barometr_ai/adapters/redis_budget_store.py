"""Współdzielony licznik budżetu tokenów na Redisie.

Wymaga extra `redis` (`uv sync --extra redis`). Bez niego import się nie powiedzie, a
`Settings` nie pozwoli wybrać tego backendu — awaria jest widoczna przy starcie, nie przy
pierwszym wywołaniu modelu.
"""

from datetime import date
from typing import Protocol

#: Klucze żyją dobę z zapasem: rozliczenie jest dzienne, a doba w UTC może się rozjechać
#: z chwilą ostatniego zapisu. Krótszy TTL kasowałby licznik w trakcie dnia, dłuższy trzymałby
#: martwe klucze bez pożytku.
_KEY_TTL_SECONDS = 48 * 60 * 60

_TOTAL_KEY = "barometr:tokens:{day}:total"
_CLIENT_KEY = "barometr:tokens:{day}:client:{client_id}"


class RedisLike(Protocol):
    """Minimalny fragment API Redisa, z którego korzysta ten adapter.

    Adapter przyjmuje ten protokół, a nie konkretny typ `redis.Redis`: dzięki temu moduł nie
    zależy od pakietu `redis` w czasie kontroli typów, a test może podstawić atrapę.
    """

    def incrby(self, name: str, amount: int) -> int: ...
    def decrby(self, name: str, amount: int) -> int: ...
    def expire(self, name: str, time: int) -> bool: ...
    def get(self, name: str) -> bytes | str | None: ...


class RedisTokenBudgetStore:
    """Liczniki w Redisie, współdzielone przez wszystkie procesy i repliki.

    `add_usage` opiera się na `INCRBY`, które jest atomowe po stronie Redisa — to właśnie ono
    zamyka wyścig, przez który dwa workery przepuszczały równolegle po żądaniu przy budżecie
    starczającym na jedno.

    Klucze niosą datę, więc rozliczenie zeruje się samo o północy UTC bez zadania cyklicznego,
    a TTL sprząta liczniki minionych dni.
    """

    def __init__(self, client: RedisLike) -> None:
        self._client = client

    @staticmethod
    def _total_key(day: date) -> str:
        return _TOTAL_KEY.format(day=day.isoformat())

    @staticmethod
    def _client_key(day: date, client_id: str) -> str:
        return _CLIENT_KEY.format(day=day.isoformat(), client_id=client_id)

    @staticmethod
    def _as_int(value: bytes | str | None) -> int:
        if value is None:
            return 0
        return int(value)

    def add_usage(self, day: date, client_id: str, tokens: int) -> int:
        total_key = self._total_key(day)
        client_key = self._client_key(day, client_id)

        total = self._client.incrby(total_key, tokens)
        self._client.incrby(client_key, tokens)

        # TTL odnawiany przy każdym zapisie: klucz żyje dobę od ostatniego użycia, więc
        # licznik nie wygaśnie w środku aktywnego dnia.
        self._client.expire(total_key, _KEY_TTL_SECONDS)
        self._client.expire(client_key, _KEY_TTL_SECONDS)

        return total

    def release(self, day: date, client_id: str, tokens: int) -> None:
        self._client.decrby(self._total_key(day), tokens)
        self._client.decrby(self._client_key(day, client_id), tokens)

    def usage_today(self, day: date) -> int:
        return self._as_int(self._client.get(self._total_key(day)))

    def usage_for_client(self, day: date, client_id: str) -> int:
        return self._as_int(self._client.get(self._client_key(day, client_id)))
