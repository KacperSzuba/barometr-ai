"""Zapisuje baseline celności klasyfikatora z faktycznego przebiegu na Golden Secie.

Uruchamiany ręcznie (`make eval-baseline`), nie przez CI: baseline ma być świadomą decyzją
człowieka po obejrzeniu wyniku, a nie liczbą, którą pipeline sam sobie podnosi.

Wynikowy `baseline.json` należy zacommitować razem ze zmianą, która celność zmieniła.
"""

import datetime
import json
from pathlib import Path

from barometr_ai.adapters.fastembed_adapter import FastEmbedAdapter
from barometr_ai.core.config import Settings
from barometr_ai.services.classifier_service import ClassifierService

BASE_DIR = Path(__file__).parent


def main() -> None:
    settings = Settings()
    embedder = FastEmbedAdapter(
        settings.embedding_model_name,
        dimension=settings.embedding_dimension,
        model_version=settings.embedding_model_version,
        needs_e5_prefix=settings.embedding_needs_e5_prefix,
        batch_size=settings.embedding_batch_size,
    )
    classifier = ClassifierService(embedder=embedder)

    with open(BASE_DIR / "golden_set.json", encoding="utf-8") as f:
        cases = json.load(f)

    correct_topics = 0
    correct_pkd = 0
    for item in cases:
        res = classifier.classify(title=item["title"], content=item["content"])
        if res.topics and res.topics[0].code == item["expected_category"]:
            correct_topics += 1
        if item["expected_pkd"] in res.primary_pkd:
            correct_pkd += 1

    total = len(cases)
    baseline = {
        "note": (
            "Ostatni zmierzony wynik harnessu na golden_set.json. Wartości muszą pochodzić "
            "z faktycznego przebiegu (`make eval-baseline`), nigdy z wpisania ręcznego — "
            "patrz AGENTS.md §4."
        ),
        "measured_at": datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds"),
        "model_version": embedder.model_version,
        "golden_set_size": total,
        "topics_accuracy": correct_topics / total,
        "pkd_accuracy": correct_pkd / total,
    }

    target = BASE_DIR / "baseline.json"
    with open(target, "w", encoding="utf-8") as f:
        json.dump(baseline, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(
        f"Zapisano {target}: N={total}, tematy {baseline['topics_accuracy'] * 100:.1f}%, "
        f"PKD {baseline['pkd_accuracy'] * 100:.1f}% (model {embedder.model_version})"
    )


if __name__ == "__main__":
    main()
