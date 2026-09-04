# ADR 0003: Brak warstwy near-duplicate w klastrowaniu L1

## Status
Zaakceptowany (2026-09-05)

## Kontekst

Specyfikacja zadania „Klastrowanie strumienia" oraz audyt z 23.08.2026 wymagają warstwy
near-duplicate: „Hash → MinHash/SimHash → centroidy online". Uzasadnienie jest kosztowe —
warstwa L1 ma wyciąć ok. 70% wolumenu, zanim cokolwiek trafi do modelu, a przedruki tej
samej depeszy przez kilkanaście redakcji to dominujący wzorzec w strumieniu.

Zastana implementacja miała wyłącznie odcisk SHA-256, który łapie przedruk znak w znak,
a więc niemal nic. Audyt słusznie wskazał tę lukę.

## Pomiar

Zaimplementowaliśmy SimHash-64 na shinglach 5-znakowych oraz — ponieważ wsad jest ograniczony
do 512 dokumentów, więc przybliżenie MinHashem nie jest potrzebne — dokładny współczynnik
Jaccarda na tych samych shinglach. Obie metody zmierzyliśmy na wariantach depeszy PL o
długości ok. 230 znaków.

| Wariant | Odległość Hamminga (SimHash) | Jaccard |
|---|---:|---:|
| przedruk: sama zmieniona data | 3–5 | 0,955 |
| przedruk: dopisany podpis redakcji | 3 | 0,912 |
| przedruk: inna interpunkcja | 3 | 0,896 |
| przedruk: dopisany lead redakcji | 11 | 0,916 |
| przedruk: data + podpis łącznie | 7 | 0,930 |
| **inny przedmiot regulacji** (energia → woda) | **7** | **0,878** |
| **inny adresat** (MŚP → duże przedsiębiorstwa) | 8–10 | **0,820** |
| **odwrócenie sensu** („obejmą" → „nie obejmą") | **2** | **0,955** |
| niezależna depesza o tym samym wydarzeniu | 25 | 0,038 |

Dwa wnioski przesądzają sprawę:

1. **Pasma się nakładają.** Przedruk z dopisanym podpisem (Jaccard 0,912) jest leksykalnie
   *mniej* podobny do oryginału niż ten sam szablon z podmienionym przedmiotem regulacji
   byłby po drobniejszej edycji. Nie istnieje próg rozdzielający te dwa zbiory.
2. **Negacja jest niewidzialna.** Zmiana „obejmą" na „nie obejmą" — odwracająca skutek
   prawny dla adresata — daje Jaccard 0,955 i odległość Hamminga 2, czyli wygląda na
   duplikat *bliższy* niż jakikolwiek prawdziwy przedruk. Każdy próg, który scala przedruki,
   scala też tę parę.

Dla tekstów krótkich (tytuły rzędu 35 znaków o wspólnym prefiksie) rozdział znika zupełnie:
zmiana daty daje 17 bitów różnicy, a zupełnie inny tytuł 19.

## Decyzja

**Nie wdrażamy warstwy near-duplicate opartej na pokryciu leksykalnym.** Klastrowanie ma
dwie warstwy:

1. Odcisk SHA-256 tekstu znormalizowanego przez zniesienie wielkości liter, interpunkcji
   i odstępów. Zniesienie interpunkcji jest jedynym rozluźnieniem względem porównania znak
   w znak — bezspornym, bo interpunkcja nie niesie treści normatywnej.
2. Aglomeracja o średnim wiązaniu na embeddingach.

Warstwa wektorowa i tak grupuje przedruki (kosinus ok. 0,99), więc rezygnacja nie oznacza,
że przedruki przestają być klastrowane. Traci się wyłącznie możliwość pominięcia dla nich
inferencji embeddingu — a ta jest lokalna i bezkosztowa. Oddawany zysk jest zerowy,
oddawane ryzyko realne.

## Konsekwencje

**Pozytywne**

- Żadne dwa dokumenty o przeciwnym znaczeniu nie zostaną scalone na poziomie L1 przez
  próg podobieństwa, którego nikt nie umie uzasadnić.
- `reduction_rate` opisuje redukcję faktycznie wykonaną przez warstwę wektorową, a nie
  sumę dwóch mechanizmów o różnej wiarygodności.
- Brak stałej progowej, której wartości nie da się wywieść z pomiaru — zgodnie z §4
  AGENTS.md.

**Negatywne — świadomie przyjęte**

- Redukcja wolumenu przed warstwą embeddingową jest mniejsza, niż zakładała specyfikacja.
  Ponieważ embedding jest lokalny i darmowy, nie przekłada się to na koszt L3.
- **Ślepota na negację pozostaje nierozwiązana i dotyczy także warstwy wektorowej.**
  Podobieństwo kosinusowe reaguje na „nie" równie słabo jak Jaccard, więc dwa dokumenty
  o przeciwnym skutku prawnym nadal mogą trafić do jednego klastra, z którego do
  streszczenia pójdzie tylko reprezentant. To ograniczenie **całej warstwy L1**, nie tylko
  odrzuconego SimHasha, i nie zostało tą decyzją naprawione — zostało jedynie przestałe
  być powiększane.

## Co odblokuje właściwe rozwiązanie

Rozdzielenie „przedruk" od „wariant o zmienionym znaczeniu" wymaga porównania twierdzeń,
a nie pokrycia leksykalnego — czyli tego samego mechanizmu, którego brak blokuje dziś klasę
`COMMENTARY` w `NoveltyDetectorService`. Naturalna kolejność: najpierw ekstrakcja twierdzeń
na modelu, potem porównanie ich na poziomie klastra. Do tego czasu ryzyko jest udokumentowane
tutaj i w docstringu `clustering_service`, a nie ukryte za progiem.
