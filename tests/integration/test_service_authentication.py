"""Bramka dostępu do warstwy inferencyjnej.

Serwis wydaje pieniądze z dziennego budżetu tokenów i widzi treść każdego żądania, więc
otwarty port jest awarią, a nie niedogodnością. Te testy pilnują trzech rzeczy: że klucz
faktycznie zamyka trasy inferencyjne, że sondy zdrowia zostają otwarte dla orkiestratora,
i że odmowa wraca w tej samej kopercie błędu co reszta API.
"""

import pytest
from httpx import ASGITransport, AsyncClient

from barometr_ai.core.config import get_settings
from barometr_ai.main import create_app

SERVICE_KEY = "klucz-testowy"


@pytest.fixture
def secured_app(monkeypatch: pytest.MonkeyPatch):
    """Aplikacja z włączoną bramką. `get_settings` jest cache'owane, więc cache leci dwa razy."""
    monkeypatch.setenv("SERVICE_API_KEY", SERVICE_KEY)
    get_settings.cache_clear()
    try:
        yield create_app()
    finally:
        get_settings.cache_clear()


@pytest.fixture
async def secured_client(secured_app):
    transport = ASGITransport(app=secured_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


async def test_zadanie_bez_klucza_dostaje_401(secured_client: AsyncClient) -> None:
    response = await secured_client.post("/v1/score", json={"stage": "sejm_committee"})

    assert response.status_code == 401
    body = response.json()
    assert body["error"] == "UNAUTHORIZED"
    assert "X-Api-Key" in body["message"]


async def test_zly_klucz_dostaje_401(secured_client: AsyncClient) -> None:
    response = await secured_client.post(
        "/v1/score", json={"stage": "sejm_committee"}, headers={"X-Api-Key": "nie-ten"}
    )

    assert response.status_code == 401


async def test_poprawny_klucz_przepuszcza(secured_client: AsyncClient) -> None:
    response = await secured_client.post(
        "/v1/score", json={"stage": "sejm_committee"}, headers={"X-Api-Key": SERVICE_KEY}
    )

    assert response.status_code == 200
    assert response.json()["model_version"] == "linear-relevance-v1.0"


@pytest.mark.parametrize("path", ["/v1/health", "/v1/ready"])
async def test_sondy_zdrowia_zostaja_otwarte(secured_client: AsyncClient, path: str) -> None:
    """Orkiestrator sprawdzający kontener nie ma jak przedstawić sekretu."""
    response = await secured_client.get(path)

    assert response.status_code != 401


async def test_pusty_klucz_w_konfiguracji_nie_zamyka_niczego(async_client: AsyncClient) -> None:
    """Domyślna konfiguracja deweloperska zostaje otwarta — produkcji broni walidator Settings."""
    response = await async_client.post("/v1/score", json={"stage": "sejm_committee"})

    assert response.status_code == 200
