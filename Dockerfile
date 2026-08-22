# Multi-stage production Dockerfile for Barometr AI
FROM python:3.13-slim AS builder

WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends build-essential && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir .

FROM python:3.13-slim AS runner

WORKDIR /app
COPY --from=builder /usr/local/lib/python3.13/site-packages /usr/local/lib/python3.13/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

COPY src/ ./src/
COPY docs/ ./docs/

ENV APP_ENV=production \
    PYTHONUNBUFFERED=1 \
    PORT=8000 \
    HOST=0.0.0.0

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/v1/health')" || exit 1

CMD ["uvicorn", "barometr_ai.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]