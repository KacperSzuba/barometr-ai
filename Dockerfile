# Multi-stage production Dockerfile for Barometr AI
FROM python:3.14-slim AS builder

# Binarka uv przypięta do konkretnego taga — Dependabot (ekosystem "docker") ją aktualizuje.
COPY --from=ghcr.io/astral-sh/uv:0.12.9 /uv /bin/uv

WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends build-essential && rm -rf /var/lib/apt/lists/*

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    # Obraz bazowy niesie już interpreter; uv nie ma dociągać własnego.
    UV_PYTHON_DOWNLOADS=never

COPY pyproject.toml uv.lock README.md ./
COPY src/ ./src/

# --frozen: build pada, gdy uv.lock rozjechał się z pyproject.toml, zamiast po cichu
# rozwiązywać zależności od nowa. --no-editable wpisuje kod do .venv, więc obraz
# runtime nie potrzebuje katalogu src/.
RUN uv sync --frozen --no-dev --no-editable

FROM python:3.14-slim AS runner

WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY docs/ ./docs/

# Pakiet jest już zainstalowany w .venv przez etap builder — kopiowanie src/ do
# obrazu runtime tworzyłoby drugą, nieimportowaną kopię kodu.

ENV PATH="/app/.venv/bin:$PATH" \
    APP_ENV=production \
    PYTHONUNBUFFERED=1 \
    PORT=8000 \
    HOST=0.0.0.0 \
    # Modele ONNX pobierają się do katalogu cache; musi być zapisywalny dla użytkownika bez roota.
    HF_HOME=/home/barometr/.cache/huggingface

RUN useradd --create-home --uid 10001 barometr && \
    mkdir -p /home/barometr/.cache && \
    chown -R barometr:barometr /home/barometr /app
USER barometr

EXPOSE 8000

# Sonda gotowości sprawdza stan modeli, nie samo działanie procesu.
HEALTHCHECK --interval=30s --timeout=5s --start-period=120s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/v1/ready', timeout=4).status==200 else 1)" || exit 1

# --workers 1 odpowiada domyślnemu TOKEN_BUDGET_BACKEND=memory: licznik budżetu żyje wtedy
# w pamięci procesu, więc N workerów dałoby limit N × DAILY_TOKEN_BUDGET. Żeby podnieść tę
# liczbę, przestaw backend na `redis` (obraz trzeba wtedy zbudować z `--extra redis`) —
# konfiguracja WORKERS>1 na liczniku w pamięci jest odrzucana przy starcie.
CMD ["uvicorn", "barometr_ai.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
