.PHONY: help install lock upgrade run test test-offline lint format typecheck check eval eval-baseline docker-build docker-run

help:
	@echo "Barometr AI - Dostępne komendy:"
	@echo "  make install     Instaluje zależności z uv.lock (dokładnie te wersje co CI)"
	@echo "  make lock        Przelicza uv.lock po zmianie zależności w pyproject.toml"
	@echo "  make upgrade     Podnosi wszystkie zależności w uv.lock do najnowszych"
	@echo "  make run         Uruchamia serwer developerski FastAPI z auto-reloadem"
	@echo "  make test        Uruchamia kompletny pakiet testów pytest"
	@echo "  make test-offline Uruchamia testy niewymagające pobrania modelu"
	@echo "  make lint        Sprawdza jakość kodu za pomocą Ruff"
	@echo "  make format      Automatycznie formatuje kod źródłowy"
	@echo "  make typecheck   Sprawdza typy (mypy --strict)"
	@echo "  make check       Uruchamia wszystkie bramki jakości tak jak CI"
	@echo "  make eval        Uruchamia testy ewaluacyjne na zbiorze referencyjnym (Golden Set)"
	@echo "  make eval-baseline Zapisuje baseline celności z realnego przebiegu"
	@echo "  make docker-build Buduje produkcyjny obraz Docker"

# --frozen: instaluj dokładnie to, co w locku; nie rozwiązuj zależności od nowa.
install:
	uv sync --frozen --extra dev

lock:
	uv lock

upgrade:
	uv lock --upgrade

run:
	uv run uvicorn barometr_ai.main:app --reload --host 0.0.0.0 --port 8000

test:
	uv run pytest -v

# Bez testów wymagających pobrania modelu — jedyny zestaw, który przechodzi offline.
test-offline:
	uv run pytest -m "not model" -v

lint:
	uv run ruff check .
	uv run ruff format --check .

format:
	uv run ruff format .
	uv run ruff check --fix .

typecheck:
	uv run mypy

check: lint typecheck test

eval:
	uv run pytest tests/evaluation -v -s

# Zapisuje baseline celności z realnego przebiegu. Świadoma decyzja człowieka — CI tego nie woła.
eval-baseline:
	uv run python tests/evaluation/record_baseline.py

docker-build:
	docker build -t barometr-ai:latest .

docker-run:
	docker run -p 8000:8000 --env-file .env barometr-ai:latest
