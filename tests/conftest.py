"""Pytest fixtures."""

import pytest
from httpx import ASGITransport, AsyncClient

from barometr_ai.main import create_app


@pytest.fixture
def app():
    return create_app()


@pytest.fixture
async def async_client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client
