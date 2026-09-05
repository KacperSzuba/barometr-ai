"""Integration tests for OpenAPI endpoints."""

import pytest


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
