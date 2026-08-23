# Multi-stage production Dockerfile for Barometr AI
FROM python:3.13-slim AS builder

WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends build-essential && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY src/ ./src/
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir .

FROM python:3.13-slim AS runner

WORKDIR /app
COPY --from=builder /usr/local/lib/python3.13/site-packages /usr/local/lib/python3.13/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY docs/ ./docs/

# Pakiet jest już zainstalowany w site-packages przez etap builder — kopiowanie src/ do
# obrazu runtime tworzyłoby drugą, nieimportowaną kopię kodu.

ENV APP_ENV=production \
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

CMD ["uvicorn", "barometr_ai.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
