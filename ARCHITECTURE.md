# Architektura Modułu Barometr AI

## 1. Cel i Zadania Modułu AI
Moduł `barometr-ai` jest niezależnym, bezstanowym mikroserwisem inferencyjnym odpowiedzialnym za przetwarzanie języka naturalnego (NLP), wektoryzację, klasyfikację, streszczanie z proweniencją, klastrowanie, prognozowanie i transkrypcję dla platformy Barometr.

## 2. Kluczowe Podsystemy i Mapowanie Wymagań

```
                        ┌──────────────────────────────────────────────┐
                        │        FastAPI REST API (v1 endpoints)       │
                        │   /embed   /classify   /cluster   /summarize │
                        │   /diff    /forecast   /transcribe  /radar   │
                        └──────────────────────┬───────────────────────┘
                                               │
               ┌───────────────────────────────┴───────────────────────────────┐
               ▼                               ▼                               ▼
    ┌──────────────────────┐       ┌──────────────────────┐       ┌──────────────────────┐
    │  Embedding & Search  │       │  Summary & Provenance│       │  Clustering & Dedup  │
    │  • MMLW / e5 PL      │       │  • Structured Prompts│       │  • MinHash / SimHash │
    │  • Chunking [chars]  │       │  • Strict Citations  │       │  • HDBSCAN (offline) │
    │  • HNSW Compatibility│       │  • LLM Cascade L1-L3 │       │  • Online Centroids  │
    └──────────────────────┘       └──────────────────────┘       └──────────────────────┘
               │                               │                               │
               ▼                               ▼                               ▼
    ┌──────────────────────┐       ┌──────────────────────┐       ┌──────────────────────┐
    │ Classification & NER │       │  Forecasting & Diffs │       │  Speech & Audio (F4) │
    │  • PKD Mapping       │       │  • Legal Tree Diff   │       │  • faster-whisper    │
    │  • Entity Extraction │       │  • RCL Comment Match │       │  • pyannote diarize  │
    │  • Silence Radar     │       │  • Calibrated Prob.  │       │  • Speaker Index     │
    └──────────────────────┘       └──────────────────────┘       └──────────────────────┘
```

---

## 3. Struktura Katalogów Projektu

```text
barometr-ai/
├── src/
│   └── barometr_ai/
│       ├── __init__.py
│       ├── main.py                  # Punkt wejścia aplikacji FastAPI
│       ├── core/                    # Konfiguracja, logowanie, telemetria (OTel)
│       │   ├── __init__.py
│       │   ├── config.py            # Ustawienia z walidacją Pydantic Settings
│       │   ├── telemetry.py         # OpenTelemetry & metryki tokenów/kosztu
│       │   └── logging.py           # Strukturalne logowanie JSON z trace_id
│       ├── domain/                  # Modele czysto domenowe (bez frameworka)
│       │   ├── __init__.py
│       │   ├── provenance.py        # Obiekty proweniencji (document_id, char_start, char_end)
│       │   ├── classification.py    # Taksonomia branż, PKD, obszarów regulacyjnych
│       │   ├── clustering.py        # Modele klastrów, centroidów i duplikatów
│       │   └── summary.py           # Modele ustrukturyzowanych streszczeń
│       ├── ports/                   # Interfejsy (abstrakcje / Protocols)
│       │   ├── __init__.py
│       │   ├── embedder.py          # Interfejs generowania wektorów
│       │   ├── classifier.py        # Interfejs klasyfikacji
│       │   └── summarizer.py        # Interfejs LLM z proweniencją
│       ├── adapters/                # Konkretne implementacje modeli i zewnętrznych API
│       │   ├── __init__.py
│       │   ├── local_embedder.py    # Implementacja modelu MMLW / FastEmbed / ONNX
│       │   ├── llm_client.py        # Klient LLM (Gemini / OpenAI) z retry i budżetem
│       │   └── speech_adapter.py    # Adapter faster-whisper i pyannote
│       ├── services/                # Logika aplikacyjna i orkiestracja
│       │   ├── __init__.py
│       │   ├── chunking_service.py  # Dzielenie tekstu z zachowaniem char_range
│       │   ├── cascade_service.py   # Kaskada kosztowa (L1 -> L2 -> L3)
│       │   └── provenance_guard.py  # Weryfikacja cytowań i odrzucanie halucynacji
│       └── api/                     # Warstwa HTTP / REST API
│           ├── __init__.py
│           ├── dependencies.py      # Dependency Injection (FastAPI Depends)
│           ├── exception_handlers.py# Mapowanie błędów domenowych na kody HTTP
│           └── v1/
│               ├── __init__.py
│               ├── router.py        # Agregator tras v1
│               ├── health.py        # Healthcheck i stan modeli
│               ├── embeddings.py    # POST /v1/embed
│               ├── classification.py# POST /v1/classify
│               ├── clustering.py    # POST /v1/cluster
│               └── summaries.py     # POST /v1/summarize
├── tests/
│   ├── conftest.py                  # Wspólne fixtury pytest
│   ├── unit/                        # Testy czysto jednostkowe (szybkie)
│   ├── integration/                 # Testy endpointów FastAPI i pipeline'ów
│   └── evaluation/                  # Golden set, baseline celności i metryki jakości
├── docs/
│   ├── adr/                         # Architecture Decision Records (ADR)
│   └── taxonomy/                    # Mapowania PKD i obszarów prawnych
├── .mcp.json                        # Konfiguracja serwerów Model Context Protocol
├── AGENTS.md                        # Standardy Clean Code i wytyczne dla agentów
├── pyproject.toml                   # Zależności i konfiguracja narzędzi
└── README.md
```
