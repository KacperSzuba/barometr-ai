# Barometr AI

Bezstanowy serwis inferencyjny platformy Barometr: embeddingi PL, klasyfikacja, klastrowanie
i streszczenia legislacyjne z bezwzględną proweniencją znakową.

## Wymagania

- Python 3.11+ (obraz produkcyjny: 3.14; CI: 3.11, 3.13, 3.14)
- [uv](https://docs.astral.sh/uv/) — menedżer zależności; instalacja na Windows:
  `powershell -c "irm https://astral.sh/uv/install.ps1 | iex"`
- Klucz Claude API dla warstwy generatywnej (`ANTHROPIC_API_KEY`)

## Start

```bash
uv sync --frozen --extra dev
cp .env.example .env
uv run uvicorn barometr_ai.main:app --reload
```

Te same kroki opakowane w `make install` / `make run`, jeśli masz `make`.

Wersje zależności są przypięte w `uv.lock` — lokalnie, w CI i w obrazie Docker
instaluje się dokładnie to samo. Po zmianie zależności w `pyproject.toml` uruchom
`uv lock`, a nowy `uv.lock` zacommituj razem ze zmianą.

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
| `POST /v1/pipeline` | **kaskada L1→L2→L3** w jednym żądaniu: klastrowanie → istotność → top-N → streszczenia |
| `POST /v1/summarize` | streszczenie z proweniencją |
| `POST /v1/score` | scoring istotności, model liniowy z jawnymi wagami |
| `POST /v1/diff` | diff aktów i korelacja z uwagami RCL |
| `POST /v1/novelty` | nowość vs recykling vs publicystyka |
| `POST /v1/ner` | ekstrakcja encji i relacji z proweniencją |
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

## Kaskada kosztowa

`POST /v1/pipeline` przepuszcza wsad przez wszystkie trzy warstwy naraz. Model językowy
widzi wyłącznie reprezentantów top-N klastrów, które przeszły próg istotności i zmieściły
się w dziennym budżecie tokenów.

Dwie rzeczy, których nie da się osiągnąć wołając warstwy osobno:

- **Rozmiar klastra zasila scoring.** `sources_count` w modelu istotności to liczba
  dokumentów w klastrze. Akt opisany przez dwanaście redakcji jest istotniejszy niż ten sam
  akt opisany raz — i wie to dopiero warstwa L1.
- **Budżet zawęża N, zamiast wywracać żądanie.** Bramka stoi *przed* wywołaniem modelu.
  Klaster ponad budżet wraca z `skip_reason`, a to, co już policzone, jest poprawnym wynikiem.

Żaden dokument nie znika po cichu: każdy klaster w odpowiedzi ma albo streszczenie, albo
jawny powód pominięcia (`poza top-N`, `istotność poniżej progu`, `budżet wyczerpany`,
`treść za krótka`). `cluster_id` jest wyprowadzony ze składu klastra, więc ten sam zestaw
dokumentów daje ten sam identyfikator między wywołaniami i backend może po nim cache'ować —
serwis pozostaje bezstanowy ([ADR 0001](docs/adr/0001-stateless-ai-service.md)).

Warstwy near-duplicate (SimHash/MinHash) w L1 świadomie nie ma — pomiar i uzasadnienie
w [ADR 0003](docs/adr/0003-brak-warstwy-near-duplicate.md).

## Relacje i publicystyka

Relacje z `/v1/ner` powstają wyłącznie tam, gdzie jedno zdanie niesie jawną konstrukcję
czasownikową („złożył … do", „nadzoruje", „sprzeciwił się") z przylegającymi do niej encjami.
Każda krawędź niesie `char_start`, `char_end` i `trigger`, więc weryfikuje się ją wobec tekstu
tak samo jak twierdzenie w streszczeniu. Zdanie złożone albo wtrącenie między encją
a czasownikiem daje zero krawędzi — precyzja przed pokryciem.

Klasa `commentary` z `/v1/novelty` nie wynika z podobieństwa wektorowego, bo publicystyka nie
jest poziomem nowości, tylko gatunkiem. Rozpoznają ją jawne zwroty opiniujące, wypisane
w polu `method`. Recykling ma przed nią pierwszeństwo: duplikat jest ukrywany niezależnie od
gatunku.

Zakres, świadome luki i warunki właściwego rozwiązania:
[ADR 0004](docs/adr/0004-relacje-i-publicystyka-z-jawnych-przeslanek.md).

## Jakość

```bash
make check
```

Uruchamia komplet bramek: `ruff check`, `ruff format --check`, `mypy --strict`, `pytest`.
Te same cztery bramki wymusza CI na macierzy Python 3.11, 3.13 i 3.14. W macierzy jest
3.14, ponieważ na tej wersji stoi obraz produkcyjny — interpreter, na którym serwis
faktycznie działa, nie może być jedynym nietestowanym.

Testy wymagające pobrania modelu embeddingów niosą marker `model`. Zestaw bez sieci:

```bash
make test-offline
```

### Golden Set i próg regresji

`tests/evaluation/golden_set.json` liczy 200 przypadków wymaganych przez `AGENTS.md` §3.1,
po 28–29 na każdy z siedmiu obszarów taksonomii. Trzy testy strukturalne pilnują zbioru
niezależnie od modelu: rozmiaru, pokrycia całej taksonomii (kategoria bez ani jednego
przypadku wygląda, jakby była mierzona) i braku powtórzeń.

Zbiór jest zredagowany ręcznie na wzór realnych tytułów i opisów legislacyjnych — nie
pochodzi z rejestrów publicznych. Zanim posłuży za twardą bramkę jakości, warto podmienić
przypadki na akty pobrane z RCL i Sejmu.

Obok progu absolutnego (75%) działa próg regresji: spadek o więcej niż 3 pkt wobec ostatniego
zapisanego pomiaru wywraca pipeline. Baseline pochodzi wyłącznie z faktycznego przebiegu:

```bash
make eval-baseline   # zapisuje tests/evaluation/baseline.json — zacommituj razem ze zmianą
```

Dopóki baseline jest pusty, test regresji jawnie się pomija, zamiast porównywać z liczbą,
której nikt nie zmierzył.

## Ograniczenia wdrożeniowe

Licznik dziennego budżetu tokenów leży za portem `TokenBudgetStorePort` i ma dwa magazyny.

| `TOKEN_BUDGET_BACKEND` | Zasięg limitu | Kiedy |
|---|---|---|
| `memory` (domyślny) | jeden proces | dev i wdrożenie jednoprocesowe; restart zeruje licznik |
| `redis` | wszystkie procesy i repliki | warunek skalowania poziomego; wymaga `uv sync --extra redis` i `REDIS_URL` |

Przy `memory` obraz startuje z `--workers 1`, a konfiguracja `WORKERS>1` **jest odrzucana
przy starcie**: N procesów liczyłoby osobno, dając limit N × `DAILY_TOKEN_BUDGET`. Cicha
dwukrotność zadeklarowanego budżetu to dokładnie ta awaria, którą ta bramka ma łapać.

Limit domyka się **po** doliczeniu, nie przed: `record_usage` dolicza atomowo, sprawdza wynik
i w razie przekroczenia cofa zapis. Kolejność „sprawdź, potem dolicz" byłaby wyścigiem — dwa
procesy odczytałyby ten sam stan sprzed zapisu i oba uznałyby, że budżet starcza.
