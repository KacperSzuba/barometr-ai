# Barometr AI

Bezstanowy serwis inferencyjny platformy Barometr: embeddingi PL, klasyfikacja, klastrowanie
i streszczenia legislacyjne z bezwzględną proweniencją znakową.

## Wymagania

- Python 3.11+ (obraz produkcyjny i CI: 3.13)
- Klucz Claude API dla warstwy generatywnej (`ANTHROPIC_API_KEY`)

## Start

```bash
make install
cp .env.example .env
make run
```

Serwis nasłuchuje na `:8000`, dokumentacja OpenAPI pod `/docs`.

Pierwszy start pobiera model embeddingów (domyślnie `intfloat/multilingual-e5-large`,
ok. 2,2 GB). Modele ładują się przy starcie aplikacji, nie przy pierwszym żądaniu.

## Architektura warstw

| Warstwa | Co robi | Koszt |
|---|---|---|
| **L1** | Embeddingi lokalne (ONNX/CPU), deduplikacja, klastrowanie | zerowy |
| **L2** | Klasyfikacja na embeddingach, detekcja nowości | zerowy |
| **L3** | Streszczenia z proweniencją na wyselekcjonowanym top-N | Claude API |

Rozdział jest istotny kosztowo: L1 wycina ok. 70% wolumenu, zanim cokolwiek trafi do modelu.

## Proweniencja

Każde twierdzenie w streszczeniu niesie `source_document_id`, `char_start` i `char_end`
wskazujące dokładne miejsce w tekście źródłowym. Odwołania pochodzą z mechanizmu cytowań
Claude API — model ich nie przepisuje — i są dodatkowo weryfikowane wobec dokumentu po
stronie serwisu. Sekcja, której nie da się zakotwiczyć, wraca do modelu z korektą, a po
wyczerpaniu prób jest odrzucana i raportowana w `rejected_sections`. Nigdy nie jest
uzupełniana zastępczą treścią.

Uzasadnienie decyzji: [ADR 0002](docs/adr/0002-proweniencja-przez-cytowania-api.md).

## Degradacja bez klucza API

Przy pustym `ANTHROPIC_API_KEY` warstwa generatywna schodzi do `HeuristicLLMAdapter` —
deterministycznego ekstraktora regułowego. Degradacja jest jawna: odpowiedzi niosą
`is_generative: false`, a `model_version` to `heuristic-v0`. Przy `APP_ENV=production`
brak klucza wywraca start serwisu.

## Endpointy

| Endpoint | Opis |
|---|---|
| `GET /v1/health` | liveness |
| `GET /v1/ready` | readiness — stan modeli, 503 gdy niegotowe |
| `POST /v1/embed` | embeddingi, `input_type` = `passage` albo `query` |
| `POST /v1/classify` | klasyfikacja tematyczna i mapowanie na PKD |
| `POST /v1/cluster` | deduplikacja i klastrowanie strumienia |
| `POST /v1/summarize` | streszczenie z proweniencją |
| `POST /v1/score` | scoring istotności, model liniowy z jawnymi wagami |
| `POST /v1/diff` | diff aktów i korelacja z uwagami RCL |
| `POST /v1/novelty` | nowość vs recykling |
| `POST /v1/ner` | ekstrakcja encji |
| `POST /v1/radar` | radar ciszy, wymaga `peer_media_mentions` |
| `POST /v1/framing` | rama medialna |
| `POST /v1/local/parse` | parser dokumentów BIP |
| `POST /v1/gov/polls` | agregacja sondaży |
| `POST /v1/gov/feedback` | skrzynka obywatelska, próg k ≥ 50 |
| `POST /v1/briefing` | **501** — niezaimplementowane |
| `POST /v1/forecast` | **501** — niezaimplementowane |

Dwa ostatnie zwracają `501`, ponieważ poprzednie implementacje odpowiadały danymi zmyślonymi.
Uzasadnienie i warunki włączenia: `AGENTS.md` §4.

Nagłówek `X-Client-Id` służy do rozliczenia zużycia tokenów per klient.

## Jakość

```bash
make check
```

Uruchamia komplet bramek: `ruff check`, `ruff format --check`, `mypy --strict`, `pytest`.
Te same cztery bramki wymusza CI na macierzy Python 3.11 i 3.13.
