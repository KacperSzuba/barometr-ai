# Barometr AI — Standardy Kodowania, Architektura & Clean Code

Plik ten stanowi nadrzędną instrukcję architektoniczną i jakościową dla modułu **Barometr AI** (`barometr-ai`). Każdy kod generowany i modyfikowany w tym projekcie musi być bezwzględnie zgodny z poniższymi regułami.

---

## 1. Filozofia i Architektura Systemu

1. **Bezstanowość (Stateless Service):**
   - Serwis AI jest czystą warstwą obliczeniową/inferencyjną.
   - **Zakaz bezpośredniego łączenia się z główną bazą biznesową aplikacji** – dane wejściowe przychodzą w payloadzie żądania (`Request DTO`), a wynik wychodzi w odpowiedzi (`Response DTO`).
   - Każda odpowiedź inferencyjna zawiera metadane: `model_version`, `prompt_version`, zużycie tokenów i czas wykonania.

2. **Ścisła Proweniencja (Strict Provenance — Zasada Nienegocjowalna):**
   - Wszelkie fakty pochodne, streszczenia, twierdzenia i powiązania generowane przez modele **muszą** wskazywać dokładne źródło:
     - `source_document_id: str`
     - `char_start: int`
     - `char_end: int`
   - Zdania generowane przez LLM bez poprawnego, zweryfikowanego odwołania do tekstu źródłowego są **odrzucane i regenerowane**.

3. **Kaskada Kosztowa (Cost Cascade):**
   - **Warstwa 1 (Lokalna/Zero-cost):** Lokalne embeddingi PL (`MMLW` / `multilingual-e5`), MinHash/SimHash, odrzucanie duplikatów i klastrowanie (redukcja ~70% wolumenu).
   - **Warstwa 2 (Fast/Cheap):** Małe modele klasyfikacyjne (kategoryzacja PKD, detekcja nowości vs recyklingu).
   - **Warstwa 3 (Large LLM):** Duże modele stosowane wyłącznie na wyselekcjonowanych `top-N` klastrach o wysokiej istotności z twardym limitem tokenów.

4. **Wytłumaczalność i Bezstronność:**
   - Wszelkie scoringi istotności opierają się na modelach liniowych/parametrycznych z jawnymi wagami („dlaczego to widzisz").
   - Brak ocen politycznych, wartościujących przymiotników i rankingów „najlepszy/najgorszy". Stosujemy wyłącznie fakty z rejestrów publicznych z jawną metodologią i pasmami błędu.

---

## 2. Standardy Clean Code w Pythonie

1. **Typowanie (Type Hints):**
   - Pełne, ścisłe typowanie w całym kodzie (PEP 484, PEP 585, PEP 604).
   - Używaj składni Pythona 3.10+ (np. `list[str]`, `str | None` zamiast `Optional[str]`, `dict[str, Any]`).
   - Zero typów `Any` w modelach domenowych i kontraktach API.

2. **Modele Danych (Pydantic V2):**
   - Wszystkie DTO (Data Transfer Objects) i konfiguracje definiujemy przez `pydantic.BaseModel` oraz `pydantic_settings.BaseSettings`.
   - Wymuszone reguły Pydantic:
     ```python
     class StrictSchema(BaseModel):
         model_config = ConfigDict(
             extra="forbid",  # Odrzucaj nieznane pola
             frozen=True,  # Niemutowalność DTO domyślnie
             str_strip_whitespace=True,
         )
     ```

3. **Struktura Kodu (Clean / Hexagonal Architecture):**
   - `src/barometr_ai/domain/` – Czyste modele domenowe, interfejsy (Protocols / ABC), wyjątki domenowe. Zero zależności od frameworków webowych czy zewnętrznych bibliotek inferencyjnych.
   - `src/barometr_ai/services/` – Logika biznesowa, orkiestracja kaskady kosztowej, chunking, walidacja proweniencji.
   - `src/barometr_ai/adapters/` – Implementacje modeli (HuggingFace, ONNX, API Gemini/OpenAI, Tokenizery).
   - `src/barometr_ai/api/` – Routery FastAPI, mapowanie DTO, kody HTTP, middleware OTel.
   - `src/barometr_ai/core/` – Konfiguracja środowiskowa (`config.py`), logowanie strukturalne, telemetria.

4. **Obsługa Błędów:**
   - Twórz dedykowane wyjątki domenowe dziedziczące po bazowym `BarometrAIError`.
   - Mapuj wyjątki domenowe na odpowiednie kody HTTP w warstwie API (`api/exception_handlers.py`).
   - Nigdy nie używaj pustych bloków `except: pass` ani łapania ogólnego `except Exception` bez zalogowania kontekstu i `trace_id`.

5. **Asynchroniczność (Async / Await):**
   - Endpointy I/O-bound (np. wywołania API, operacje sieciowe) implementujemy jako `async def`.
   - Operacje intensywne CPU (np. inferencja lokalnego modelu PyTorch/ONNX, ciężki chunking) wykonujemy w puli wątków/procesów (`asyncio.to_thread` lub dedykowane workery), aby nie blokować pętli zdarzeń (`Event Loop`).

---

## 3. Testowanie i Ewaluacja (Quality Assurance)

1. **Piramida Testów:**
   - **Testy jednostkowe (`tests/unit`):** Szybkie, bez zewnętrznych zależności, 100% deterministyczne.
   - **Testy integracyjne (`tests/integration`):** Sprawdzają kontrakty FastAPI (`httpx.AsyncClient`) oraz ładowanie modeli.
   - **Harness ewaluacyjny (`tests/evaluation`):** Testy jakościowe na zbiorze **Golden Set (200 dokumentów)**:
     - Sprawdzanie poprawności odwołań proweniencji (`char_range`).
     - Metryki F1 dla klasyfikatorów.
     - Próg regresji (spadek > 3 pkt blokuje pipeline CI/CD).

2. **Narzędzia QA:**
   - Formatowanie i Linting: `ruff check .` oraz `ruff format .`
   - Sprawdzanie typów: `mypy --strict src`
   - Uruchamianie testów: `pytest -v --asyncio-mode=auto`

---

## 4. Reguła Zakazu Stałych Pewnościowych

Wprowadzona po audycie z 23.08.2026, w którym dziesięć pól odpowiedzi API zwracało wartości
wpisane wprost w kod, podane odbiorcy jako dane pochodne (m.in. `neutrality_score=0.88`,
`correlation_confidence=0.85`, `historical_base_rate=0.82`, margines błędu sondażu 2,8 pkt
identyczny dla partii z 3% i z 35%).

**Reguła:** żadne pole typu `score`, `confidence`, `probability`, `margin`, `rate` ani
`expected_*` nie może mieć w kodzie serwisu wartości literalnej.

Dopuszczalne są dokładnie trzy warianty:

1. **Policzone z wejścia żądania** — wraz z polem opisującym metodę
   (`method`, `correlation_method`, `methodology_note`), żeby wynik dało się wytłumaczyć.
2. **`None` z jawnym powodem w opisie pola** — gdy pomiar nie jest zaimplementowany.
   `None` jest uczciwą odpowiedzią; zmyślona liczba nie jest.
3. **Nazwana stała progowa na poziomie modułu** — próg decyzyjny (`MIN_RELEVANCE`,
   `ANOMALY_RATIO`, `Z_95`), a nie wynik pomiaru. Musi mieć komentarz uzasadniający wartość.

**Endpoint, który nie umie policzyć swojego wyniku, zwraca `501`, a nie prawdopodobną liczbę.**
Dotyczy to w szczególności produktu, którego obietnicą jest weryfikowalna proweniencja:
poprawnie ustrukturyzowana odpowiedź ze zmyśloną treścią przechodzi każdy walidator schematu
i każdy test kontraktowy, a jest dokładnie tą awarią, przed którą cała architektura chroni.

**Metadane odpowiedzi muszą opisywać to, co faktycznie wykonało inferencję.** `model_version`
i `prompt_version` nie mogą być stałymi z konfiguracji, gdy żaden model nie został wywołany.
Wynik adaptera zastępczego zawsze niesie `is_generative=false`.
