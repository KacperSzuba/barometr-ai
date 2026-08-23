"""Radar Ciszy - detekcja anomalii braku pokrycia medialnego dla istotnych ustaw (F2)."""

import statistics

from barometr_ai.domain.advanced_models import (
    SilenceRadarRequest,
    SilenceRadarResponse,
)

#: Akty poniżej tego progu istotności nie trafiają na listę — inaczej sygnał tonie w drobiazgach.
MIN_RELEVANCE = 55.0
#: Ile razy poniżej mediany porównywalnych aktów musi być pokrycie, żeby uznać je za anomalię.
ANOMALY_RATIO = 0.25
#: Minimalna liczba aktów porównywalnych, żeby mediana miała jakąkolwiek moc.
MIN_PEERS = 5


class SilenceRadarService:
    """Wykrywa akty o wysokiej wadze merytorycznej, które przeszły bez rozgłosu.

    Oczekiwane pokrycie liczone jest z faktycznej historii aktów porównywalnych, które
    dostarcza wywołujący — backend ma te dane, serwis AI jest bezstanowy. Poprzednia wersja
    używała wzoru zamkniętego `(istotność/100)^2 * 35 * współczynnik` z dwiema stałymi
    wpisanymi w kod, więc wynik nie zależał od żadnej historii.
    """

    @staticmethod
    def evaluate(request: SilenceRadarRequest) -> SilenceRadarResponse:
        peers = request.peer_media_mentions

        if len(peers) < MIN_PEERS:
            return SilenceRadarResponse(
                expected_mentions=None,
                silence_gap=None,
                is_anomaly=False,
                explanation=(
                    f"Za mało aktów porównywalnych do wyznaczenia oczekiwanego pokrycia "
                    f"(otrzymano {len(peers)}, wymagane co najmniej {MIN_PEERS})."
                ),
            )

        expected = float(statistics.median(peers))
        gap = max(0.0, expected - request.actual_media_mentions)
        is_anomaly = (
            request.relevance_score >= MIN_RELEVANCE
            and request.actual_media_mentions <= expected * ANOMALY_RATIO
        )

        if is_anomaly:
            explanation = (
                f"Anomalia: akt o istotności {request.relevance_score}/100 ma "
                f"{request.actual_media_mentions} wzmianek, przy medianie {expected:.1f} "
                f"dla {len(peers)} aktów porównywalnych na etapie {request.stage.value}."
            )
        else:
            explanation = (
                f"Pokrycie ({request.actual_media_mentions} wzmianek) mieści się w zakresie "
                f"typowym dla aktów porównywalnych (mediana {expected:.1f}, n={len(peers)})."
            )

        return SilenceRadarResponse(
            expected_mentions=round(expected, 1),
            silence_gap=round(gap, 1),
            is_anomaly=is_anomaly,
            explanation=explanation,
        )
