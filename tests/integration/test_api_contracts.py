"""Integration tests for OpenAPI endpoints."""

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.mark.asyncio
@pytest.mark.model
async def test_embed_endpoint(async_client):
    payload = {"texts": ["Ustawa o cenach energii", "Projekt rozporzadzenia"]}
    response = await async_client.post("/v1/embed", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 2
    assert len(data["embeddings"]) == 2
    assert data["dimension"] > 0


@pytest.mark.asyncio
async def test_summarize_endpoint(async_client):
    payload = {
        "document_id": "druk_sejmu_123",
        "content": "Nowelizacja ustawy o odnawialnych źródłach energii wprowadza ułatwienia dla instalacji fotowoltaicznych.",
    }
    response = await async_client.post("/v1/summarize", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["document_id"] == "druk_sejmu_123"
    assert len(data["summary_bullets"]) > 0
    assert len(data["summary_bullets"][0]["provenance"]) > 0


async def test_nieobsluzona_awaria_wraca_z_identyfikatorem_sladu(app):
    """Gołe 500 bez `trace_id` nie da się powiązać ze zgłoszeniem klienta.

    `raise_app_exceptions=False` jest tu konieczne: Starlette wysyła odpowiedź z handlera,
    a potem podnosi wyjątek dalej, żeby trafił do logów serwera. Domyślny transport testowy
    przechwyciłby go zamiast oddać odpowiedź, której ten test dotyczy.
    """

    @app.get("/v1/_test_boom")
    async def _boom() -> None:
        raise RuntimeError("awaria spoza hierarchii domenowej")

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        res = await client.get("/v1/_test_boom")

    assert res.status_code == 500
    body = res.json()
    assert body["error"] == "INTERNAL_ERROR"
    # Treść wyjątku nie wycieka do odpowiedzi — zostaje w logu razem z trace_id.
    assert "awaria spoza hierarchii domenowej" not in res.text
