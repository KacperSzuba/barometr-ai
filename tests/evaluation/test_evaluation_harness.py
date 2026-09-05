"""Harness Ewaluacyjny i Testy Regresji Jakościowej (Wymóg F1)."""

import json
from pathlib import Path

import pytest

from barometr_ai.services.classifier_service import REGULATORY_TAXONOMY, ClassifierService

#: Harness jakościowy z definicji potrzebuje realnego modelu.
pytestmark = pytest.mark.model

GOLDEN_SET_PATH = Path(__file__).parent / "golden_set.json"
BASELINE_PATH = Path(__file__).parent / "baseline.json"

#: Próg absolutny: poniżej tej celności klasyfikator nie nadaje się do produkcji,
#: niezależnie od tego, czy poprzedni pomiar był lepszy czy gorszy.
MIN_ACCURACY = 0.75

#: Maksymalny dopuszczalny spadek względem ostatniego zapisanego pomiaru, w punktach
#: procentowych. Wartość z AGENTS.md §3.1 („spadek > 3 pkt blokuje pipeline").
MAX_REGRESSION_POINTS = 3.0


def _measure(classifier: ClassifierService, cases: list[dict[str, str]]) -> tuple[float, float]:
    """Zwraca (celność tematów, celność PKD) na zbiorze referencyjnym."""
    correct_topics = 0
    correct_pkd = 0

    for item in cases:
        res = classifier.classify(title=item["title"], content=item["content"])
        if res.topics and res.topics[0].code == item["expected_category"]:
            correct_topics += 1
        if item["expected_pkd"] in res.primary_pkd:
            correct_pkd += 1

    total = len(cases)
    return correct_topics / total, correct_pkd / total


@pytest.fixture(scope="module")
def classifier(embedder) -> ClassifierService:
    return ClassifierService(embedder=embedder)


@pytest.fixture(scope="module")
def golden_cases() -> list[dict[str, str]]:
    with open(GOLDEN_SET_PATH, encoding="utf-8") as f:
        cases: list[dict[str, str]] = json.load(f)
    return cases


def test_golden_set_pokrywa_cala_taksonomie(golden_cases: list[dict[str, str]]) -> None:
    """Zbiór, w którym brakuje kategorii, nie mierzy jej regresji — a wygląda, jakby mierzył."""
    taxonomy = {area.code: set(area.pkd_codes) for area in REGULATORY_TAXONOMY}
    covered = {case["expected_category"] for case in golden_cases}
    assert covered == set(taxonomy), f"kategorie bez przypadku: {set(taxonomy) - covered}"

    # Oczekiwany kod PKD spoza taksonomii danej kategorii jest nieosiągalny — taki przypadek
    # zaniżałby metrykę bez względu na jakość modelu.
    for case in golden_cases:
        assert case["expected_pkd"] in taxonomy[case["expected_category"]], case["id"]


def test_golden_set_classification_benchmark(
    classifier: ClassifierService, golden_cases: list[dict[str, str]]
) -> None:
    """Celność klasyfikacji na zbiorze referencyjnym: próg absolutny i próg regresji."""
    accuracy_topics, accuracy_pkd = _measure(classifier, golden_cases)

    print(
        f"\n[Golden Set] N={len(golden_cases)}, celność tematów: {accuracy_topics * 100:.1f}%, "
        f"celność PKD: {accuracy_pkd * 100:.1f}%"
    )

    assert accuracy_topics >= MIN_ACCURACY
    assert accuracy_pkd >= MIN_ACCURACY


def test_brak_regresji_wobec_zapisanego_pomiaru(
    classifier: ClassifierService, golden_cases: list[dict[str, str]]
) -> None:
    """Blokuje spadek celności o więcej niż `MAX_REGRESSION_POINTS` wobec baseline'u.

    Baseline musi pochodzić z faktycznego przebiegu — nie jest wpisywany ręcznie. Dopóki go
    nie zapisano, test nie udaje, że mierzy regresję, tylko jawnie ją pomija (AGENTS.md §4:
    brak pomiaru to `None` z powodem, nie prawdopodobna liczba).
    """
    with open(BASELINE_PATH, encoding="utf-8") as f:
        baseline = json.load(f)

    if baseline.get("topics_accuracy") is None or baseline.get("pkd_accuracy") is None:
        pytest.skip(
            "Brak zapisanego baseline'u celności. Zapisz go z realnego przebiegu: "
            "`make eval-baseline`, a wynikowy tests/evaluation/baseline.json zacommituj."
        )

    accuracy_topics, accuracy_pkd = _measure(classifier, golden_cases)

    drop_topics = (baseline["topics_accuracy"] - accuracy_topics) * 100
    drop_pkd = (baseline["pkd_accuracy"] - accuracy_pkd) * 100

    assert drop_topics <= MAX_REGRESSION_POINTS, (
        f"Celność tematów spadła o {drop_topics:.1f} pkt wobec baseline'u "
        f"({baseline['topics_accuracy'] * 100:.1f}% → {accuracy_topics * 100:.1f}%)."
    )
    assert drop_pkd <= MAX_REGRESSION_POINTS, (
        f"Celność PKD spadła o {drop_pkd:.1f} pkt wobec baseline'u "
        f"({baseline['pkd_accuracy'] * 100:.1f}% → {accuracy_pkd * 100:.1f}%)."
    )
