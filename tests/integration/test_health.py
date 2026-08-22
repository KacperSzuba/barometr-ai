"""Integration test for health endpoint."""

import pytest


@pytest.mark.asyncio
async def test_health_check(async_client):
    response = await async_client.get("/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["stateless"] is True
