"""Porównanie framingu redakcji prasowych i analiza interesariuszy (F3)."""

from barometr_ai.domain.enterprise_models import (
    FramingAnalysisRequest,
    FramingAnalysisResponse,
    FramingType,
    MediaOutletFraming,
)

#: Sygnały leksykalne per rama. Materiał trafia do ramy z największą liczbą trafień;
#: remis oznacza brak rozstrzygnięcia, nie pierwszą pasującą regułę.
_FRAMING_SIGNALS: dict[FramingType, tuple[str, ...]] = {
    FramingType.COST_OF_LIVING: (
        "cen",
        "podat",
        "koszt",
        "portfel",
        "rachun",
        "podwyżk",
        "drożej",
        "opłat",
        "budżet domow",
    ),
    FramingType.PROCEDURAL: (
        "sejm",
        "senat",
        "głosowan",
        "czytani",
        "termin",
        "komisj",
        "druk",
        "vacatio",
        "konsultacj",
    ),
    FramingType.POLITICAL: (
        "opozycj",
        "koalicj",
        "spór",
        "parti",
        "polityczn",
        "rząd upad",
        "konflikt",
        "atak",
    ),
    FramingType.EXPERT: (
        "ekspert",
        "analiz",
        "badani",
        "raport",
        "prawnik",
        "ekonomist",
        "wskaźnik",
        "dane",
    ),
}


class StakeholderFramingService:
    """Bezstronna analiza ramy ujęcia tematu w mediach, bez rankingów i ocen redakcji.

    Świadome ograniczenie: klasyfikacja jest leksykalna, nie semantyczna. Nie mierzy tonu
    ani neutralności — poprzednia wersja zwracała `neutrality_score=0.88` jako stałą wpisaną
    w kod oraz zdanie o ujawnieniu właściciela w KRS, którego nie sprawdzała. Oba pola
    zwracają teraz `None`. Zadanie F3 wymaga tonu mierzonego wobec sprawy i jawnego pasma
    błędu — a punkt 4 specyfikacji zakazuje agregacji do rankingu przyjazny/wrogi.
    """

    @staticmethod
    def analyze_framing(request: FramingAnalysisRequest) -> FramingAnalysisResponse:
        outlets: list[MediaOutletFraming] = []

        for article in request.articles:
            haystack = f"{article.get('title', '')} {article.get('content', '')}".lower()
            scores = {
                framing: sum(1 for signal in signals if signal in haystack)
                for framing, signals in _FRAMING_SIGNALS.items()
            }
            best = max(scores.values())
            winners = [framing for framing, score in scores.items() if score == best]
            # Zero trafień albo remis = brak rozstrzygnięcia. Zgadywanie ramy jest oceną.
            dominant = winners[0] if best > 0 and len(winners) == 1 else None

            outlets.append(
                MediaOutletFraming(
                    outlet_name=article.get("outlet", "Redakcja nieznana"),
                    dominant_framing=dominant,
                    framing_signal_count=best,
                    neutrality_score=None,
                    ownership_transparency=None,
                )
            )

        resolved = {outlet.dominant_framing for outlet in outlets if outlet.dominant_framing}
        classified = sum(1 for outlet in outlets if outlet.dominant_framing)

        return FramingAnalysisResponse(
            cluster_id=request.cluster_id,
            outlets=outlets,
            # Udział rozpoznanych ram wśród sklasyfikowanych materiałów, nie stała /4.
            framing_diversity_score=(round(len(resolved) / classified, 2) if classified else 0.0),
            unclassified_count=len(outlets) - classified,
        )
