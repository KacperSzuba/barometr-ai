.PHONY: help install run test lint format eval docker-build docker-run

help:
	@echo "Barometr AI - Dostępne komendy:"
	@echo "  make install     Instaluje zależności w środowisku wirtualnym"
	@echo "  make run         Uruchamia serwer developerski FastAPI z auto-reloadem"
	@echo "  make test        Uruchamia kompletny pakiet testów pytest"
	@echo "  make lint        Sprawdza jakość kodu za pomocą Ruff"
	@echo "  make format      Automatycznie formatuje kod źródłowy"
	@echo "  make eval        Uruchamia testy ewaluacyjne na zbiorze referencyjnym (Golden Set)"
	@echo "  make docker-build Buduje produkcyjny obraz Docker"

install:
	pip install -e ".[dev]"

run:
	uvicorn barometr_ai.main:app --reload --host 0.0.0.0 --port 8000

test:
	pytest -v

lint:
	ruff check .

format:
	ruff format .
	ruff check --fix .

eval:
	pytest tests/evaluation -v -s

docker-build:
	docker build -t barometr-ai:latest .

docker-run:
	docker run -p 8000:8000 barometr-ai:latest