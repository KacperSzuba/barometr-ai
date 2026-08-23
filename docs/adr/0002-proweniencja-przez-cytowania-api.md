# ADR 0002: Proweniencja przez cytowania dostawcy zamiast przepisywania cytatu

## Status
Zaakceptowany (2026-08-23)

## Kontekst

Zadanie F1 „Streszczenia LLM top-N z zachowaniem proweniencji" stawia warunek nieusuwalny:
każde zdanie musi wskazywać `document_id` + `char_range`, a zdanie bez poprawnego odwołania
jest odrzucane i regenerowane.

Pierwsza implementacja realizowała to tak: prompt kazał modelowi skopiować cytat znak w znak
do pola JSON, a serwis szukał tego ciągu w dokumencie przez `str.find()`.

Metoda działa, ale ma wbudowaną wadę. Model normalizuje tekst: zamienia półpauzę na dywiz,
zwija podwójną spację, poprawia literówkę ze skanu OCR. Każda taka zmiana powoduje, że
`find()` nie trafia — i merytorycznie poprawne zdanie zostaje odrzucone. Odrzucenie kosztuje
regenerację, a regeneracja kosztuje tokeny. Im dłuższy i brudniejszy dokument, tym gorszy
ten kompromis. Jednocześnie metoda nie chroni przed przypadkiem odwrotnym: model może
wygenerować ciąg, który przypadkiem występuje w dokumencie w innym kontekście.

## Decyzja

1. Dokument źródłowy przekazujemy dostawcy jako **osobny blok treści** z włączonymi
   cytowaniami (`citations: {"enabled": true}`), a nie wklejony w treść promptu.
2. Odwołania odbieramy z odpowiedzi jako `char_location` (`start_char_index`,
   `end_char_index`) i mapujemy wprost na `ProvenanceSpan`.
3. **Walidator pozostaje.** `ProvenanceService.to_provenance_span()` sprawdza każdy offset
   wobec tekstu źródłowego i odrzuca odwołanie, gdy `cited_text` nie zgadza się z wycinkiem
   dokumentu. To obrona w głąb, nie zaufanie do dostawcy.
4. Sekcje odpowiedzi wymuszamy promptem i rozpoznajemy po znacznikach
   (`[CO_SIE_ZMIENIA]`, `[KOGO_DOTYCZY]`, `[CO_DALEJ]`, `[USTALENIA_DODATKOWE]`).
5. Sekcja bez podstawy w dokumencie wraca jako `BRAK_PODSTAWY` i jest poprawną odpowiedzią,
   a nie awarią — nie uruchamia regeneracji.

## Konsekwencje

**Pozytywne**

- Model nie przepisuje offsetów, więc nie ma ich jak zmyślić. Znika najczęstsza klasa
  fałszywych odrzuceń, a wraz z nią koszt regeneracji.
- Punkt 7 zadania F1 („kliknięcie w zdanie podświetla fragment oryginału") wychodzi wprost
  z kontraktu, bez dodatkowej pracy po stronie UI.
- `HeuristicLLMAdapter` realizuje ten sam kontrakt, licząc offsety lokalnie — obie ścieżki
  przechodzą przez identyczny walidator.

**Negatywne — świadomie przyjęte**

- **Cytowania wykluczają wyjścia strukturalne.** `output_config.format` razem z `citations`
  zwraca HTTP 400. Tracimy gwarancję parsowalnego JSON i musimy parsować znaczniki
  (`services/section_parser.py`). Parsowanie znaczników jest ryzykiem operacyjnym —
  zmyślony cytat byłby ryzykiem produktowym. Wymiana jest opłacalna.
- Odwołania stronicowe (PDF `page_location`) nie mają odpowiednika w `ProvenanceSpan`
  i są pomijane. Dokumenty PDF wymagają wcześniejszej ekstrakcji do tekstu.

## Wpływ na koszt

Punkt cachowania (`cache_control: ephemeral`) stoi na bloku dokumentu, więc obejmuje prompt
systemowy i cały dokument. Przy regeneracji odrzuconych sekcji ten sam dokument jedzie
ponownie i czyta się z cache za ułamek ceny wejścia — a to on stanowi większość żądania.
