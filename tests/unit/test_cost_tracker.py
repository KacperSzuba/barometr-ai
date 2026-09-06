"""Testy jednostkowe modułu śledzenia budżetu tokenów i limitów kosztowych."""

import datetime

import fakeredis
import pytest

from barometr_ai.adapters.in_memory_budget_store import InMemoryTokenBudgetStore
from barometr_ai.adapters.redis_budget_store import RedisTokenBudgetStore
from barometr_ai.core.exceptions import BudgetExceededError
from barometr_ai.ports.token_budget import TokenBudgetStorePort
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


# --- Magazyn liczników: zachowanie wspólne dla obu implementacji ---


@pytest.fixture(params=["memory", "redis"])
def budget_store(request) -> TokenBudgetStorePort:
    """Ten sam zestaw asercji dla obu adapterów — kontrakt portu nie może się rozjeżdżać."""
    if request.param == "memory":
        return InMemoryTokenBudgetStore()

    fake = fakeredis.FakeRedis()
    return RedisTokenBudgetStore(fake)


DAY = datetime.date(2026, 9, 5)
NEXT_DAY = datetime.date(2026, 9, 6)


def test_store_dolicza_i_zwraca_stan_po_zapisie(budget_store: TokenBudgetStorePort) -> None:
    assert budget_store.add_usage(DAY, "client_1", 100) == 100
    assert budget_store.add_usage(DAY, "client_2", 50) == 150
    assert budget_store.usage_today(DAY) == 150
    assert budget_store.usage_for_client(DAY, "client_1") == 100
    assert budget_store.usage_for_client(DAY, "client_2") == 50


def test_store_cofa_doliczenie(budget_store: TokenBudgetStorePort) -> None:
    budget_store.add_usage(DAY, "client_1", 100)
    budget_store.release(DAY, "client_1", 100)
    assert budget_store.usage_today(DAY) == 0
    assert budget_store.usage_for_client(DAY, "client_1") == 0


def test_store_rozlicza_dni_osobno(budget_store: TokenBudgetStorePort) -> None:
    budget_store.add_usage(DAY, "client_1", 100)
    assert budget_store.usage_today(NEXT_DAY) == 0
    assert budget_store.add_usage(NEXT_DAY, "client_1", 30) == 30


def test_store_nieznany_klient_i_dzien_to_zero(budget_store: TokenBudgetStorePort) -> None:
    assert budget_store.usage_today(DAY) == 0
    assert budget_store.usage_for_client(DAY, "nigdy_nie_widziany") == 0


# --- Sedno P0-5: limit obowiązuje wspólnie dla procesów dzielących magazyn ---


def test_wspoldzielony_magazyn_domyka_limit_dla_dwoch_instancji() -> None:
    """Dwa „procesy" na jednym magazynie mają jeden budżet, a nie po jednym każdy.

    To jest regresja na awarię z audytu: przy liczniku w pamięci procesu `--workers 2`
    dawało dwukrotność deklarowanego limitu.
    """
    shared = RedisTokenBudgetStore(fakeredis.FakeRedis())
    worker_a = CostTrackerService(daily_budget=1000, store=shared)
    worker_b = CostTrackerService(daily_budget=1000, store=shared)

    worker_a.record_usage(client_id="client_1", tokens=800)

    # Drugi worker widzi wydatek pierwszego i odmawia, zamiast otwierać własny budżet.
    assert worker_b.can_afford(800) is False
    with pytest.raises(BudgetExceededError):
        worker_b.record_usage(client_id="client_1", tokens=800)

    assert worker_b.tokens_today == 800


def test_liczniki_w_pamieci_nie_sa_wspoldzielone() -> None:
    """Dokumentuje ograniczenie domyślnego backendu — powód, dla którego obraz ma WORKERS=1."""
    worker_a = CostTrackerService(daily_budget=1000)
    worker_b = CostTrackerService(daily_budget=1000)

    worker_a.record_usage(client_id="client_1", tokens=900)

    assert worker_a.tokens_today == 900
    assert worker_b.tokens_today == 0  # osobna pamięć = osobny budżet


def test_odrzucone_zadanie_nie_zostawia_sladu_w_liczniku() -> None:
    """Bramka dolicza przed sprawdzeniem, więc odrzucenie musi cofnąć zapis co do tokena."""
    tracker = CostTrackerService(daily_budget=1000)
    tracker.record_usage(client_id="client_1", tokens=600)

    with pytest.raises(BudgetExceededError):
        tracker.record_usage(client_id="client_1", tokens=600)

    assert tracker.tokens_today == 600
    assert tracker.usage_for_client("client_1") == 600


def test_enforce_false_ksieguje_ponad_budzet() -> None:
    """Tokenów wydanych u dostawcy nie da się cofnąć — muszą trafić do licznika."""
    tracker = CostTrackerService(daily_budget=1000)
    status = tracker.record_usage(client_id="client_1", tokens=1500, enforce=False)

    assert status["tokens_today"] == 1500
    assert tracker.can_afford(1) is False
