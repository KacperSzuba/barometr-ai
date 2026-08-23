"""Agregator sondaży i Skrzynka Obywatelska z twardym progiem prywatności k >= 50 (F5 Gov)."""

import math
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


class GovAnalyticsService:
    """Analityka dla sektora publicznego z twardo wymuszonymi bezpiecznikami prywatności."""

    @staticmethod
    def aggregate_polls(request: PollsAggregateRequest) -> PollsAggregateResponse:
        """Uśrednia sondaże z jawną metodologią i policzonym pasmem błędu."""
        pooled = GovAnalyticsService._weighted_average(request.polls)
        effective_sample = sum(poll.sample_size for poll in request.polls)

        # Pasmo błędu zależy od wielkości próby ORAZ od szacowanego udziału. Stała wartość
        # dla każdej partii była statystycznie nieprawdziwa zarówno przy 3%, jak i przy 35%.
        error_margins = {
            party: GovAnalyticsService._margin_of_error(share, effective_sample)
            for party, share in pooled.items()
        }

        house_effects = GovAnalyticsService._house_effects(request.polls, pooled)

        return PollsAggregateResponse(
            pooled_average=pooled,
            confidence_error_margins=error_margins,
            house_effects=house_effects,
            methodology_note=(
                f"Średnia ważona wielkością próby z {len(request.polls)} sondaży "
                f"(łączna próba {effective_sample}). Pasmo błędu: przedział 95% dla frakcji, "
                f"z = {Z_95:.2f}, liczone z łącznej próby i szacowanego udziału. "
                "Efekt domu sondażowego liczony metodą leave-one-out — ośrodek porównywany "
                "jest do średniej BEZ jego własnych sondaży, żeby nie zaniżać odchylenia. "
                "Pasmo obejmuje wyłącznie błąd losowania; nie obejmuje błędu doboru próby "
                "ani różnic metodologicznych między ośrodkami."
            ),
        )

    @staticmethod
    def _weighted_average(polls: list[PollItem]) -> dict[str, float]:
        totals: dict[str, float] = defaultdict(float)
        weights: dict[str, float] = defaultdict(float)
        for poll in polls:
            weight = float(poll.sample_size)
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
        polls: list[PollItem], pooled: dict[str, float]
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
            baseline = GovAnalyticsService._weighted_average(others)
            own = GovAnalyticsService._weighted_average(
                [poll for poll in polls if poll.pollster == pollster]
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
    def process_citizen_feedback(request: CitizenFeedbackRequest) -> CitizenFeedbackResponse:
        """Klastruje opinie i wymusza próg k >= 50 (wymóg prawny AI Act i ochrony prywatności)."""
        min_k = request.min_k_threshold

        topic_counts: dict[str, list[str]] = defaultdict(list)
        for msg in request.messages:
            lowered = msg.message.lower()
            if "cen" in lowered or "prąd" in lowered:
                topic = "Koszty energii i ogrzewania"
            elif "szkoł" in lowered or "edukacj" in lowered:
                topic = "Edukacja i opieka przedszkolna"
            else:
                topic = "Inne sprawy lokalne"
            topic_counts[topic].append(msg.message)

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
