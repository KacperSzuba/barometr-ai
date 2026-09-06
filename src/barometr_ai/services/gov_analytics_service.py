"""Agregator sondaży i Skrzynka Obywatelska z twardym progiem prywatności k >= 50 (F5 Gov)."""

import datetime
import math
import re
from collections import defaultdict

from barometr_ai.domain.enterprise_models import (
    CitizenFeedbackRequest,
    CitizenFeedbackResponse,
    FeedbackCluster,
    PollItem,
    PollsAggregateRequest,
    PollsAggregateResponse,
)

#: Wartość krytyczna rozkładu normalnego dla dwustronnego przedziału 95%.
Z_95 = 1.959964

#: Reguły przypisania zgłoszenia do obszaru tematycznego: rdzenie dopasowywane **od początku
#: wyrazu**, w kolejności sprawdzania. Granica wyrazu jest tu konieczna, a nie kosmetyczna —
#: dopasowanie dowolnym podciągiem wiązało rdzeń „cen" z wyrazem „ocena", więc zgłoszenie
#: „Ocena pracy szkoły jest niska" trafiało do obszaru kosztów energii.
#:
#: To dopasowanie słów kluczowych, nie klastrowanie semantyczne: obszar spoza tej listy
#: wpada do kosza „Inne sprawy lokalne", a nie tworzy własnego tematu.
_FEEDBACK_TOPIC_STEMS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Koszty energii i ogrzewania", ("cen", "prąd", "prad", "ogrzewan", "rachun", "opał", "opal")),
    ("Edukacja i opieka przedszkolna", ("szkoł", "szkol", "edukacj", "przedszkol", "żłob", "zlob")),
)

_FALLBACK_TOPIC = "Inne sprawy lokalne"

_FEEDBACK_TOPIC_PATTERNS: tuple[tuple[str, tuple[re.Pattern[str], ...]], ...] = tuple(
    (topic, tuple(re.compile(r"\b" + re.escape(stem)) for stem in stems))
    for topic, stems in _FEEDBACK_TOPIC_STEMS
)


class GovAnalyticsService:
    """Analityka dla sektora publicznego z twardo wymuszonymi bezpiecznikami prywatności."""

    @staticmethod
    def aggregate_polls(request: PollsAggregateRequest) -> PollsAggregateResponse:
        """Uśrednia sondaże z jawną metodologią i policzonym pasmem błędu."""
        # Kotwicą zaniku jest najnowszy sondaż w zestawie, nie „dziś": serwis jest bezstanowy,
        # a wynik ma być odtwarzalny. Zegar w wzorze sprawiłby, że to samo żądanie zwraca
        # z czasem inne liczby, więc backend nie mógłby po nim cache'ować ani go odtworzyć.
        anchor = max(poll.date for poll in request.polls)
        pooled = GovAnalyticsService._weighted_average(
            request.polls, anchor=anchor, half_life_days=request.half_life_days
        )
        effective_sample = sum(poll.sample_size for poll in request.polls)

        # Pasmo błędu zależy od wielkości próby ORAZ od szacowanego udziału. Stała wartość
        # dla każdej partii była statystycznie nieprawdziwa zarówno przy 3%, jak i przy 35%.
        error_margins = {
            party: GovAnalyticsService._margin_of_error(share, effective_sample)
            for party, share in pooled.items()
        }

        house_effects = GovAnalyticsService._house_effects(
            request.polls, anchor=anchor, half_life_days=request.half_life_days
        )

        return PollsAggregateResponse(
            pooled_average=pooled,
            confidence_error_margins=error_margins,
            house_effects=house_effects,
            methodology_note=(
                f"Średnia ważona z {len(request.polls)} sondaży (łączna próba "
                f"{effective_sample}). Waga = wielkość próby × zanik wykładniczy świeżości: "
                f"sondaż starszy o {request.half_life_days} dni od najnowszego w zestawie "
                f"({anchor.isoformat()}) waży połowę. Pasmo błędu: przedział 95% dla frakcji, "
                f"z = {Z_95:.2f}, liczone z łącznej próby i szacowanego udziału. "
                "Efekt domu sondażowego liczony metodą leave-one-out — ośrodek porównywany "
                "jest do średniej BEZ jego własnych sondaży, żeby nie zaniżać odchylenia. "
                "Pasmo obejmuje wyłącznie błąd losowania; nie obejmuje błędu doboru próby "
                "ani różnic metodologicznych między ośrodkami."
            ),
        )

    @staticmethod
    def _poll_weight(poll: PollItem, *, anchor: datetime.date, half_life_days: int) -> float:
        """Waga sondażu: wielkość próby przemnożona przez zanik wykładniczy świeżości.

        Sondaż starszy o `half_life_days` od kotwicy waży połowę tego, co sondaż z kotwicy.
        Zanik jest ciągły, więc nie ma progu, na którym waga skacze — a `half_life_days`
        przestaje być parametrem, który nic nie robi.
        """
        age_days = (anchor - poll.date).days
        # Adnotacja konieczna: `float ** float` ma pod mypy typ Any, a funkcja deklaruje float.
        decay: float = 0.5 ** (age_days / half_life_days)
        return float(poll.sample_size) * decay

    @staticmethod
    def _weighted_average(
        polls: list[PollItem], *, anchor: datetime.date, half_life_days: int
    ) -> dict[str, float]:
        totals: dict[str, float] = defaultdict(float)
        weights: dict[str, float] = defaultdict(float)
        for poll in polls:
            weight = GovAnalyticsService._poll_weight(
                poll, anchor=anchor, half_life_days=half_life_days
            )
            for party, value in poll.results.items():
                totals[party] += value * weight
                weights[party] += weight
        return {
            party: round(total / weights[party], 2)
            for party, total in totals.items()
            if weights[party]
        }

    @staticmethod
    def _margin_of_error(share_percent: float, sample_size: int) -> float:
        """Połowa szerokości przedziału 95% dla frakcji, w punktach procentowych."""
        if sample_size <= 0:
            return 0.0
        p = min(max(share_percent / 100.0, 0.0), 1.0)
        return round(Z_95 * math.sqrt(p * (1.0 - p) / sample_size) * 100.0, 2)

    @staticmethod
    def _house_effects(
        polls: list[PollItem], *, anchor: datetime.date, half_life_days: int
    ) -> dict[str, dict[str, float]]:
        """Odchylenie ośrodka od średniej policzonej BEZ jego własnych sondaży.

        Porównanie do średniej zawierającej dany ośrodek jest endogeniczne i systematycznie
        zaniża efekt — tym mocniej, im mniej sondaży w puli.
        """
        pollsters = {poll.pollster for poll in polls}
        effects: dict[str, dict[str, float]] = {}

        for pollster in pollsters:
            others = [poll for poll in polls if poll.pollster != pollster]
            if not others:
                # Jeden ośrodek w puli — nie ma do czego porównać. Brak wyniku jest
                # uczciwszy niż zero sugerujące zerowy efekt.
                continue
            # Kotwica jest wspólna dla wszystkich podzbiorów, także tych bez najnowszego
            # sondażu: liczona osobno dla każdego przesuwałaby skalę wag i odchylenie
            # mieszałoby efekt ośrodka z efektem innego punktu odniesienia w czasie.
            baseline = GovAnalyticsService._weighted_average(
                others, anchor=anchor, half_life_days=half_life_days
            )
            own = GovAnalyticsService._weighted_average(
                [poll for poll in polls if poll.pollster == pollster],
                anchor=anchor,
                half_life_days=half_life_days,
            )
            deviations = {
                party: round(value - baseline[party], 2)
                for party, value in own.items()
                if party in baseline
            }
            if deviations:
                effects[pollster] = deviations

        return effects

    @staticmethod
    def _topic_for(message: str) -> str:
        """Przypisuje zgłoszenie do obszaru po pierwszej pasującej regule."""
        lowered = message.lower()
        for topic, patterns in _FEEDBACK_TOPIC_PATTERNS:
            if any(pattern.search(lowered) for pattern in patterns):
                return topic
        return _FALLBACK_TOPIC

    @staticmethod
    def process_citizen_feedback(request: CitizenFeedbackRequest) -> CitizenFeedbackResponse:
        """Klastruje opinie i wymusza próg k >= 50 (wymóg prawny AI Act i ochrony prywatności)."""
        min_k = request.min_k_threshold

        topic_counts: dict[str, list[str]] = defaultdict(list)
        for msg in request.messages:
            topic_counts[GovAnalyticsService._topic_for(msg.message)].append(msg.message)

        clusters: list[FeedbackCluster] = []
        suppressed_count = 0

        for topic, messages in topic_counts.items():
            count = len(messages)
            if count >= min_k:
                clusters.append(
                    FeedbackCluster(
                        topic=topic,
                        # Nie jest to parafraza treści zgłoszeń — to opis zbioru. Realna
                        # parafraza wymaga modelu językowego i osobnej bramki prywatności.
                        paraphrase_summary=(
                            f"Zgłoszenia przypisane do obszaru '{topic}' na podstawie "
                            f"dopasowania słów kluczowych ({count} szt.)."
                        ),
                        count=count,
                        # Sentyment nie jest mierzony. `None` zamiast zmyślonej etykiety.
                        sentiment=None,
                    )
                )
            else:
                suppressed_count += count

        return CitizenFeedbackResponse(
            clusters=clusters,
            suppressed_count_below_k=suppressed_count,
            privacy_guarantee=f"Guardrail aktywny: Dane poniżej progu k={min_k} nie opuszczają bazy.",
        )
