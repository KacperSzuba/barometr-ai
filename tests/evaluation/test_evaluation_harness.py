"""Harness Ewaluacyjny i Testy Regresji Jakościowej (Wymóg F1)."""

import json
from pathlib import Path

import pytest

from barometr_ai.adapters.fastembed_adapter import FastEmbedAdapter
from barometr_ai.services.classifier_service import ClassifierService


@pytest.fixture(scope="module")
def classifier() -> ClassifierService:
    embedder = FastEmbedAdapter()
    return ClassifierService(embedder=embedder)


def test_golden_set_classification_benchmark(classifier: ClassifierService) -> None:
    """Sprawdza dokładność klasyfikacji na zbiorze referencyjnym (Golden Set). Cel: Accuracy >= 0.75."""
    golden_set_path = Path(__file__).parent / "golden_set.json"
    with open(golden_set_path, encoding="utf-8") as f:
        cases = json.load(f)

    correct_topics = 0
    correct_pkd = 0
    total = len(cases)

    for item in cases:
        res = classifier.classify(title=item["title"], content=item["content"])
        if res.topics and res.topics[0].code == item["expected_category"]:
            correct_topics += 1
        if item["expected_pkd"] in res.primary_pkd:
            correct_pkd += 1

    accuracy_topics = correct_topics / total
    accuracy_pkd = correct_pkd / total

    print(f"\n[Golden Set] Celność tematów: {accuracy_topics*100:.1f}%, Celność PKD: {accuracy_pkd*100:.1f}%")

    # Wymóg jakościowy: celność nie może spaść poniżej 75%
    assert accuracy_topics >= 0.75
    assert accuracy_pkd >= 0.75