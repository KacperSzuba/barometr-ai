"""Testy integracyjne dla tras API F2-F5."""

import pytest


@pytest.mark.asyncio
async def test_novelty_endpoint(async_client):
    payload = {
        "new_text": "Projekt ustawy o cenach energii wpłynął do laski marszałkowskiej.",
        "history_texts": ["Sejm debatuje nad budżetem państwa."],
    }
    res = await async_client.post("/v1/novelty", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert "classification" in data
    assert data["novelty_score"] >= 0.0


@pytest.mark.asyncio
async def test_ner_endpoint(async_client):
    payload = {"text": "Minister Finansów Jan Kowalski przekazał projekt do Sejm."}
    res = await async_client.post("/v1/ner", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert len(data["entities"]) > 0


@pytest.mark.asyncio
async def test_framing_endpoint(async_client):
    payload = {
        "cluster_id": "c10",
        "articles": [
            {"outlet": "Gazeta A", "title": "Ceny energii podskoczą", "content": "Koszty"},
            {
                "outlet": "Gazeta B",
                "title": "Awantura w Sejmie o wiatraki",
                "content": "Spór partyjny",
            },
        ],
    }
    res = await async_client.post("/v1/framing", json=payload)
    assert res.status_code == 200
    assert len(res.json()["outlets"]) == 2


@pytest.mark.asyncio
async def test_briefing_endpoint(async_client):
    payload = {
        "topic": "Energetyka jądrowa",
        "document_ids": ["d_1"],
        "timeframe_months": 6,
        "raw_texts": ["Rząd przyjął uchwałę o lokalizacji pierwszej elektrowni jądrowej w Polsce."],
    }
    res = await async_client.post("/v1/briefing", json=payload)
    # Endpoint jest świadomie wyłączony: poprzednia implementacja zwracała stałą oś czasu
    # z zaszytymi datami niezależnie od wejścia. 501 jest uczciwszy niż zmyślone dane.
    assert res.status_code == 501
    assert res.json()["detail"]["error"] == "NOT_IMPLEMENTED"


@pytest.mark.asyncio
async def test_forecast_endpoint_is_disabled(async_client):
    payload = {
        "stage": "sejm_committee",
        "sponsor_type": "GOVERNMENT",
        "days_in_current_stage": 40,
        "governing_coalition_support": True,
    }
    res = await async_client.post("/v1/forecast", json=payload)
    # Base rates były stałymi w kodzie podawanymi jako częstości historyczne.
    assert res.status_code == 501
    assert res.json()["detail"]["error"] == "NOT_IMPLEMENTED"


@pytest.mark.asyncio
async def test_local_parse_endpoint(async_client):
    payload = {
        "bip_text": "Uchwała Nr V/10/2026 w sprawie budżetu gminy na rok 2026 z kwotą 15000000 zł.",
        "gmina_teryt": "020101",
    }
    res = await async_client.post("/v1/local/parse", json=payload)
    assert res.status_code == 200
    assert res.json()["doc_type"] == "budget_uchwala"


@pytest.mark.asyncio
async def test_gov_endpoints(async_client):
    # 1. Sondaże
    polls_payload = {
        "polls": [
            {
                "pollster": "IBRiS",
                "sample_size": 1000,
                "date": "2026-08-01",
                "results": {"Partia A": 33.0},
            },
            {
                "pollster": "CBOS",
                "sample_size": 1000,
                "date": "2026-08-05",
                "results": {"Partia A": 35.0},
            },
        ]
    }
    res_polls = await async_client.post("/v1/gov/polls", json=polls_payload)
    assert res_polls.status_code == 200
    assert "Partia A" in res_polls.json()["pooled_average"]

    # 2. Skrzynka obywatelska
    fb_payload = {
        "messages": [
            {"id": f"m_{i}", "message": "Prosimy o remont drogi gminnej."} for i in range(55)
        ],
        "min_k_threshold": 50,
    }
    res_fb = await async_client.post("/v1/gov/feedback", json=fb_payload)
    assert res_fb.status_code == 200
    assert len(res_fb.json()["clusters"]) == 1
