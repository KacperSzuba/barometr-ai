"""Testy jednostkowe klasyfikatora tematycznego i mapowania PKD."""

import pytest

#: Klasyfikacja opiera się na podobieństwie semantycznym.
pytestmark = pytest.mark.model

from barometr_ai.services.classifier_service import ClassifierService


@pytest.fixture(scope="module")
def classifier(embedder) -> ClassifierService:
    return ClassifierService(embedder=embedder)


def test_classify_energy_law(classifier: ClassifierService) -> None:
    title = "Projekt ustawy o zmianie ustawy o odnawialnych źródłach energii"
    content = "Celem projektu jest rozwój farm wiatrowych oraz wsparcie prosumentów fotowoltaiki i sieci przesyłowych."

    response = classifier.classify(title, content)

    assert len(response.topics) > 0
    top_topic = response.topics[0]
    assert top_topic.code == "REG_ENERGY_OZE"
    assert "35.11.Z" in response.primary_pkd
    assert top_topic.confidence > 0.50


def test_classify_tax_law(classifier: ClassifierService) -> None:
    title = "Ustawa o podatku od towarów i usług oraz o podatku dochodowym"
    content = "Nowelizacja wprowadza obowiązkowy Krajowy System e-Faktur (KSeF) dla przedsiębiorców i rozliczeń VAT."

    response = classifier.classify(title, content)

    assert len(response.topics) > 0
    top_topic = response.topics[0]
    assert top_topic.code == "REG_TAX_FINANCE"
    assert "69.20.Z" in response.primary_pkd
