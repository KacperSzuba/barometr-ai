# ADR 0001: Bezstanowa Architektura Serwisu AI (FastAPI + Strict Provenance)

## Status
Zaakceptowany (2026-08-22)

## Kontekst
Platforma Barometr wymaga zaawansowanego przetwarzania tekstu prawnego (NLP, embeddingi, klastrowanie, klasyfikacja tematyczna, streszczenia LLM).

## Decyzja
1. Moduł AI (`barometr-ai`) jest wdrażany jako bezstanowy mikroserwis w Pythonie (FastAPI).
2. Brak bezpośredniego dostępu do bazy operacyjnej PostgreSQL — komunikacja wyłącznie przez wersjonowane kontrakty HTTP/OpenAPI `/v1/*`.
3. Każde streszczenie i fakt pochodny musi zawierać atrybuty proweniencji (`source_document_id`, `char_start`, `char_end`). Zdania bez weryfikowalnego źródła są odrzucane.
4. Kaskada kosztowa: 3 warstwy (L1: deduplikacja/lokalne embeddingi -> L2: klasyfikator -> L3: LLM na top-N).

## Konsekwencje
- Łatwa skalowalność horyzontalna serwisu inferencyjnego.
- Czyste oddzielenie cyklu wydawniczego modeli od logiki biznesowej backendu.
- Pełna audytowalność i odporność na halucynacje modeli.
