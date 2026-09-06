# ADR 0004: Relacje NER i klasa COMMENTARY wyłącznie z jawnych przesłanek

## Status
Zaakceptowany (2026-09-05)

## Kontekst

Dwa pola kontraktu API były zadeklarowane, ale nigdy nie wypełniane, i w obu przypadkach
z tego samego powodu — poprzednie implementacje wypełniały je zgadywanką, którą audyt
słusznie usunął:

1. **`NERResponse.relations`** zwracało pustą listę. Wcześniejsza wersja łączyła pierwszą
   wykrytą osobę z pierwszą instytucją krawędzią `SUBMITTED_TO` niezależnie od treści zdania.
   Relacja wyprowadzona z kolejności encji na liście nie jest wykryta, tylko wymyślona.
2. **`NoveltyType.COMMENTARY`** nigdy nie było zwracane. Klasyfikacja opierała się wyłącznie
   na maksymalnym podobieństwie kosinusowym do historii, a publicystyka nie leży na tej osi
   — nie jest poziomem nowości, tylko gatunkiem.

Pytanie brzmiało: czy zostawić oba puste do czasu wdrożenia modelu NER i porównywania
twierdzeń, czy da się wypełnić je tak, żeby każdy wynik dało się wskazać palcem w tekście.

## Decyzja

**Wypełniamy oba, ale wyłącznie z przesłanek jawnych i cytowalnych.**

### Relacje

Krawędź powstaje tylko wtedy, gdy w **jednym zdaniu** stoi konstrukcja czasownikowa
z zamkniętej listy (`złożył … do`, `zgłosił poprawkę do`, `nadzoruje`, `sprzeciwił się`,
`powiadomił` i formy pokrewne), a po obu jej stronach **przylegają** encje — między encją
a czasownikiem wolno stać wyłącznie białym znakom.

`EntityRelation` niesie `char_start`, `char_end` i `trigger`, więc każdą krawędź da się
zweryfikować wobec tekstu źródłowego dokładnie tak, jak twierdzenie w streszczeniu.

Reguła przylegania odrzuca dwa przypadki, których serwis nie umie rozstrzygnąć:

| Zdanie | Co robi reguła | Dlaczego |
|---|---|---|
| „Nowak złożył wniosek do Sejmu **oraz** powiadomił UOKiK" | zwraca tylko `Nowak → Sejm` | podmiotem powiadomienia jest Nowak (podmiot współdzielony), a sąsiadujący Sejm jest dopełnieniem poprzedniego członu |
| „zgłosił poprawkę do **projektu, a** Minister Lis…" | nie zwraca krawędzi `AMENDED` | encja po czasowniku należy już do następnego zdania składowego |
| „Sejm obradował. Senat przyjął ustawę." | nie zwraca krawędzi | relacja nigdy nie przekracza granicy zdania |

Oba odrzucenia wymagałyby analizy składniowej. Zamiast ją udawać, tracimy krawędź prawdziwą.

### Publicystyka

`COMMENTARY` wynika z zamkniętej listy zwrotów, które **same w sobie** znaczą, że autor
podaje opinię: pierwszoosobowych („moim zdaniem", „uważam, że") albo wprost metatekstowych
(„felieton", „komentarz redakcyjny"). Zwroty dopuszczające odczytanie sprawozdawcze
(„należy zauważyć", „warto dodać") są świadomie poza listą — wpuszczałyby zwykłe depesze.

Jeden trafiony zwrot wystarcza. Próg „co najmniej dwa" byłby stałą, której nie da się wywieść
z pomiaru, a więc naruszałby §4 `AGENTS.md`.

**Recykling ma pierwszeństwo przed publicystyką.** Materiał powtarzający znany tekst jest
ukrywany niezależnie od gatunku: bezpiecznikiem jest tu powtórzenie, nie forma.

Trafione zwroty trafiają do pola `method`, więc decyzja jest audytowalna po stronie odbiorcy.

## Konsekwencje

**Pozytywne**

- Żadne z obu pól nie niesie już wartości, której nie da się wskazać w tekście źródłowym.
- Relacje mają proweniencję znakową na równi ze streszczeniami — ten sam mechanizm weryfikacji.
- Rozpoznanie publicystyki jest rozpoznaniem gatunku, nie oceną treści: serwis nadal nie
  orzeka, czy opinia jest słuszna, co utrzymuje §1.4 `AGENTS.md`.

**Negatywne — świadomie przyjęte**

- **Pokrycie relacji jest niskie.** Zdanie złożone, strona bierna, szyk przestawny i wtrącenie
  między encją a czasownikiem dają zero krawędzi. Wymiana jest jednostronna z premedytacją:
  precyzja przed pokryciem.
- **Tożsamość encji nadal nierozstrzygana.** „min. Nowak" i „Minister Adam Nowak" pozostają
  dwiema encjami, więc krawędzie tej samej osoby nie łączą się w jeden węzeł grafu.
- **Lista zwrotów opiniujących jest z definicji niepełna** i nie obejmuje publicystyki pisanej
  bezosobowo — a to znaczna jej część. Tekst opiniujący bez żadnego zwrotu z listy trafi do
  `NEW_EVENT` albo `ELABORATION` dokładnie jak wcześniej.
- Rozróżnienie `RECYCLED` od `ELABORATION` **nie zostało tą decyzją ruszone** i nadal opiera
  się na podobieństwie wektorowym, nie na twierdzeniach.

## Co odblokuje właściwe rozwiązanie

To samo, co w [ADR 0003](0003-brak-warstwy-near-duplicate.md): ekstrakcja twierdzeń na modelu
i porównywanie ich zamiast pokrycia leksykalnego. Dla relacji dochodzi model NER dla polskiego
ze słownikiem instytucji i rozstrzyganiem tożsamości; dla publicystyki — klasyfikator gatunku
uczony na materiale, a nie lista zwrotów. Do tego czasu oba mechanizmy zwracają mniej, niż
widać w tekście, i jest to zapisane tutaj oraz w docstringach obu serwisów.
