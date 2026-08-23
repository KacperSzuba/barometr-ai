"""Kompletny zestaw testów integracyjnych dla wszystkich tras API v1."""

import pytest


@pytest.mark.asyncio
async def test_health_endpoint(async_client):
    res = await async_client.get("/v1/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_embed_endpoint(async_client):
    payload = {"texts": ["Ustawa o podatku dochodowym", "Nowelizacja kodeksu pracy"]}
    res = await async_client.post("/v1/embed", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["count"] == 2
    assert len(data["embeddings"]) == 2
    assert data["dimension"] == 384


@pytest.mark.asyncio
async def test_classify_endpoint(async_client):
    payload = {
        "title": "Projekt ustawy o planowaniu i zagospodarowaniu przestrzennym",
        "content": "Ustawa określa zasady sporządzania planów ogólnych gmin oraz warunków zabudowy i MPZP.",
    }
    res = await async_client.post("/v1/classify", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert len(data["topics"]) > 0
    assert data["topics"][0]["code"] == "REG_REAL_ESTATE"
    assert "68.10.Z" in data["primary_pkd"]


@pytest.mark.asyncio
async def test_cluster_endpoint(async_client):
    payload = {
        "documents": [
            {"id": "doc_1", "content": "Sejm uchwalił nowe stawki podatku akcyzowego."},
            {"id": "doc_2", "content": "Sejm uchwalił nowe stawki podatku akcyzowego."},
            {"id": "doc_3", "content": "Ministerstwo Zdrowia ogłasza listę leków refundowanych."},
        ],
        "threshold": 0.70,
    }
    res = await async_client.post("/v1/cluster", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["total_processed"] == 3
    assert len(data["clusters"]) == 2


@pytest.mark.asyncio
async def test_summarize_endpoint_with_provenance(async_client):
    text = (
        "Projekt ustawy o zmianie ustawy o gospodarce nieruchomościami wprowadza uproszczone procedury wywłaszczeń. "
        "Nowe przepisy mają wejść w życie z dniem 1 stycznia 2027 roku."
    )
    payload = {
        "document_id": "druk_890",
        "content": text,
        "max_sentences": 2,
    }
    res = await async_client.post("/v1/summarize", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["document_id"] == "druk_890"
    assert len(data["summary_bullets"]) > 0

    # Sprawdzenie, czy każdy wygenerowany fakt ma poprawną proweniencję
    for bullet in data["summary_bullets"]:
        assert len(bullet["provenance"]) > 0
        span = bullet["provenance"][0]
        assert span["source_document_id"] == "druk_890"
        assert text[span["char_start"] : span["char_end"]] == span["exact_quote"]
