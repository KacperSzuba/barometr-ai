"""Klasyfikator tematyczny aktów prawnych i mapowanie na branże/PKD."""

from dataclasses import dataclass

import numpy as np

from barometr_ai.domain.models import ClassifyResponse, TopicCategory
from barometr_ai.ports.embedder import EmbedderPort


@dataclass(frozen=True)
class RegulatoryArea:
    code: str
    label: str
    description: str
    pkd_codes: list[str]


# Baza wiedzy taksonomii Barometru (obszary regulacyjne + kody PKD)
REGULATORY_TAXONOMY: list[RegulatoryArea] = [
    RegulatoryArea(
        code="REG_ENERGY_OZE",
        label="Energetyka i Odnawialne Źródła Energii (OZE)",
        description="Energia elektryczna, odnawialne źródła energii OZE, morskie i lądowe farmy wiatrowe offshore onshore, fotowoltaika, biometan, gaz, sieci przesyłowe, taryfy energetyczne i ceny prądu.",
        pkd_codes=["35.11.Z", "35.12.Z", "35.13.Z", "35.14.Z"],
    ),
    RegulatoryArea(
        code="REG_TAX_FINANCE",
        label="Podatki, Finanse i Księgowość",
        description="Podatki dochodowe PIT, CIT, podatek od towarów i usług VAT, akcyza, KSeF e-faktury, ordynacja podatkowa, rachunkowość, rynki kapitałowe i bankowość.",
        pkd_codes=["64.19.Z", "66.19.Z", "69.20.Z"],
    ),
    RegulatoryArea(
        code="REG_REAL_ESTATE",
        label="Nieruchomości, Budownictwo i Planowanie Przestrzenne",
        description="Prawo budowlane, plany ogólne gmin, MPZP, warunki zabudowy, obrót nieruchomościami, deweloperzy, gospodarka nieruchomościami, zagospodarowanie przestrzenne.",
        pkd_codes=["41.10.Z", "41.20.Z", "68.10.Z", "68.20.Z"],
    ),
    RegulatoryArea(
        code="REG_DIGITAL_TECH",
        label="Technologie Cyfrowe, Cyberbezpieczeństwo i AI",
        description="Cyberbezpieczeństwo, dyrektywa NIS2, KSC, sztuczna inteligencja AI Act, usługi cyfrowe, e-doręczenia, ochrona danych osobowych RODO, telekomunikacja i oprogramowanie IT.",
        pkd_codes=["62.01.Z", "62.02.Z", "62.09.Z", "63.11.Z"],
    ),
    RegulatoryArea(
        code="REG_HEALTHCARE",
        label="Ochrona Zdrowia i Farmacja",
        description="Szpitale, lekarze, refundacja leków, wyroby medyczne, prawo farmaceutyczne, Narodowy Fundusz Zdrowia NFZ, apteki, świadczenia medyczne.",
        pkd_codes=["86.10.Z", "86.21.Z", "47.73.Z", "21.20.Z"],
    ),
    RegulatoryArea(
        code="REG_TRANSPORT",
        label="Transport, Spedycja i Logistyka",
        description="Transport drogowy towarów i osób, transport kolejowy i lotniczy, logistyka, spedycja, magazynowanie, czas pracy kierowców, opłaty drogowe.",
        pkd_codes=["49.41.Z", "49.20.Z", "52.10.B", "52.29.C"],
    ),
    RegulatoryArea(
        code="REG_ENVIRONMENT",
        label="Ochrona Środowiska i Gospodarka Odpadami",
        description="Gospodarka odpadami, system kaucyjny, recykling, emisje gazów cieplarnianych CO2, pozwolenia środowiskowe, gospodarka wodna, parki narodowe.",
        pkd_codes=["38.11.Z", "38.21.Z", "38.32.Z", "39.00.Z"],
    ),
]


class ClassifierService:
    """Klasyfikuje dokument prawny na podstawie podobieństwa semantycznego do taksonomii."""

    def __init__(self, embedder: EmbedderPort) -> None:
        self._embedder = embedder
        self._area_descriptions = [f"{a.label}. {a.description}" for a in REGULATORY_TAXONOMY]
        self._area_vectors = self._embedder.embed_texts(self._area_descriptions, normalize=True)

    def classify(self, title: str, content: str, threshold: float = 0.30) -> ClassifyResponse:
        """Przypisuje dokument do obszarów regulacyjnych i generuje listę właściwych kodów PKD."""
        sample_text = f"{title}. {content[:1000]}"
        doc_vector = self._embedder.embed_texts([sample_text], normalize=True)[0]

        scored_areas: list[tuple[RegulatoryArea, float]] = []
        doc_arr = np.array(doc_vector)

        for area, area_vec in zip(REGULATORY_TAXONOMY, self._area_vectors):
            score = float(np.dot(doc_arr, np.array(area_vec)))
            scored_areas.append((area, score))

        # Sortujemy malejąco po wyniku
        scored_areas.sort(key=lambda item: item[1], reverse=True)

        matched_topics: list[TopicCategory] = []
        matched_pkd: set[str] = set()

        # Zawsze bierzemy najlepszy wynik (argmax)
        if scored_areas:
            best_area, best_score = scored_areas[0]
            matched_topics.append(
                TopicCategory(
                    code=best_area.code,
                    label=best_area.label,
                    confidence=round(best_score, 3),
                )
            )
            for pkd in best_area.pkd_codes:
                matched_pkd.add(pkd)

            # Dodatkowe etykiety jeśli przekraczają próg i są blisko najlepszego wyniku
            for area, score in scored_areas[1:]:
                if score >= threshold and score >= best_score * 0.85:
                    matched_topics.append(
                        TopicCategory(
                            code=area.code,
                            label=area.label,
                            confidence=round(score, 3),
                        )
                    )
                    for pkd in area.pkd_codes:
                        matched_pkd.add(pkd)

        overall_confidence = matched_topics[0].confidence if matched_topics else 0.0

        return ClassifyResponse(
            topics=matched_topics,
            primary_pkd=sorted(matched_pkd),
            confidence_score=overall_confidence,
            model_version=self._embedder.model_name,
        )
