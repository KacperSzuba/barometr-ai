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
        label="Energetyka i Odnawialne Źródła Energii",
        description="Wytwarzanie, dystrybucja i handel energią elektryczną, gazem, biomasą, farmy wiatrowe, fotowoltaika, sieci przesyłowe, taryfy energetyczne.",
        pkd_codes=["35.11.Z", "35.12.Z", "35.13.Z", "35.14.Z"],
    ),
    RegulatoryArea(
        code="REG_TAX_FINANCE",
        label="Podatki, Finanse i Rachunkowość",
        description="Podatki dochodowe PIT, CIT, podatek od towarów i usług VAT, akcyza, ordynacja podatkowa, KSeF, rachunkowość, rynki finansowe i bankowość.",
        pkd_codes=["64.19.Z", "66.19.Z", "69.20.Z"],
    ),
    RegulatoryArea(
        code="REG_REAL_ESTATE",
        label="Nieruchomości, Budownictwo i Planowanie Przestrzenne",
        description="Prawo budowlane, planowanie i zagospodarowanie przestrzenne, MPZP, warunki zabudowy, obrót nieruchomościami, najem, gospodarka gruntami.",
        pkd_codes=["41.10.Z", "41.20.Z", "68.10.Z", "68.20.Z"],
    ),
    RegulatoryArea(
        code="REG_DIGITAL_TECH",
        label="Technologie Cyfrowe, Telekomunikacja i AI",
        description="Cyberbezpieczeństwo, AI Act, usługi cyfrowe, telekomunikacja, ochrona danych osobowych RODO, e-doręczenia, handel elektroniczny.",
        pkd_codes=["62.01.Z", "62.02.Z", "62.09.Z", "63.11.Z"],
    ),
    RegulatoryArea(
        code="REG_HEALTHCARE",
        label="Ochrona Zdrowia i Farmacja",
        description="Refundacja leków, wyroby medyczne, szpitale, NFZ, apteki, prawo farmaceutyczne, świadczenia opieki zdrowotnej.",
        pkd_codes=["86.10.Z", "86.21.Z", "47.73.Z", "21.20.Z"],
    ),
    RegulatoryArea(
        code="REG_TRANSPORT",
        label="Transport, Spedycja i Logistyka",
        description="Transport drogowy, kolejowy, lotniczy, morski, czas pracy kierowców, tachografy, opłaty drogowe, magazynowanie i spedycja.",
        pkd_codes=["49.41.Z", "49.20.Z", "52.10.B", "52.29.C"],
    ),
    RegulatoryArea(
        code="REG_ENVIRONMENT",
        label="Ochrona Środowiska i Gospodarka Odpadami",
        description="Gospodarka o obiegu zamkniętym, system kaucyjny, ROP, emisje CO2, ETS, pozwolenia zintegrowane, gospodarka wodna.",
        pkd_codes=["38.11.Z", "38.21.Z", "38.32.Z", "39.00.Z"],
    ),
]


class ClassifierService:
    """Klasyfikuje dokument prawny na podstawie podobieństwa semantycznego do taksonomii."""

    def __init__(self, embedder: EmbedderPort) -> None:
        self._embedder = embedder
        # Wyliczamy i cache'ujemy wektory opisów kategorii taksonomicznych
        self._area_descriptions = [f"{a.label}. {a.description}" for a in REGULATORY_TAXONOMY]
        self._area_vectors = self._embedder.embed_texts(self._area_descriptions, normalize=True)

    def classify(self, title: str, content: str, threshold: float = 0.40) -> ClassifyResponse:
        """Przypisuje dokument do obszarów regulacyjnych i generuje listę właściwych kodów PKD."""
        sample_text = f"{title}. {content[:1000]}"
        doc_vector = self._embedder.embed_texts([sample_text], normalize=True)[0]

        matched_topics: list[TopicCategory] = []
        matched_pkd: set[str] = set()

        doc_arr = np.array(doc_vector)
        for area, area_vec in zip(REGULATORY_TAXONOMY, self._area_vectors):
            score = float(np.dot(doc_arr, np.array(area_vec)))
            if score >= threshold:
                matched_topics.append(
                    TopicCategory(
                        code=area.code,
                        label=area.label,
                        confidence=round(score, 3),
                    )
                )
                for pkd in area.pkd_codes:
                    matched_pkd.add(pkd)

        # Sortujemy od najwyższego wyniku pewności
        matched_topics.sort(key=lambda t: t.confidence, reverse=True)

        overall_confidence = matched_topics[0].confidence if matched_topics else 0.0

        return ClassifyResponse(
            topics=matched_topics,
            primary_pkd=sorted(matched_pkd),
            confidence_score=overall_confidence,
            model_version=self._embedder.model_name,
        )