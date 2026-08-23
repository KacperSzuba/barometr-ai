"""Ekstrakcja encji (NER) i relacji w aktach i materiałach prawnych (F2)."""

import re

from barometr_ai.domain.enterprise_models import (
    EntityRelation,
    EntityType,
    ExtractedEntity,
    NERRequest,
    NERResponse,
)

_INSTITUTION_PATTERNS: list[tuple[str, EntityType]] = [
    (
        r"(Ministerstw[a-ząćęłńóśźż]+\s+[A-ZĄĆĘŁŃÓŚŹŻ][a-ząćęłńóśźż]+(?:\s+i\s+[A-ZĄĆĘŁŃÓŚŹŻ]?[a-ząćęłńóśźż]+)*)",
        EntityType.INSTITUTION,
    ),
    (r"\b(Sejm\s+Rzeczypospolitej\s+Polskiej|Sejmu?|Senatu?)\b", EntityType.INSTITUTION),
    (
        r"\b(Urząd\s+Ochrony\s+Konkurencji\s+i\s+Konsumentów|UOKiK|KNF|URE|UODO|GUS)\b",
        EntityType.INSTITUTION,
    ),
    (
        r"\b(Naczelny\s+Sąd\s+Administracyjny|Trybunał\s+Konstytucyjny|Sąd\s+Najwyższy)\b",
        EntityType.INSTITUTION,
    ),
]

#: Tytuł + nazwisko, opcjonalnie z imieniem. Obsługuje skróty ("min. Nowak") i formy pełne.
_PERSON_PATTERN = re.compile(
    r"\b(?:Minister|Ministra|Ministrowi|min\.|Premier|Premiera|Poseł|Posła|Senator|Senatora|Marszałek|Marszałka)"
    r"\s+(?:[A-ZĄĆĘŁŃÓŚŹŻ][a-ząćęłńóśźż]+\s+)?[A-ZĄĆĘŁŃÓŚŹŻ][a-ząćęłńóśźż]+"
)


class EntityExtractorService:
    """Rozpoznaje ministrów, posłów, resorty i instytucje w tekście.

    Świadome ograniczenie: to ekstrakcja wzorcami, nie NER. Nie rozstrzyga tożsamości
    ("min. Nowak" nie jest łączone z "Minister Adam Nowak") i nie wyznacza ról procesowych.
    Zadanie F2 wymaga modelu NER dla polskiego i słowników instytucji — do tego czasu
    `relations` pozostaje puste, bo relacja zgadnięta z kolejności encji w tekście jest
    zmyślona, a nie wykryta.
    """

    @staticmethod
    def extract_entities(request: NERRequest) -> NERResponse:
        text = request.text
        entities: list[ExtractedEntity] = []
        seen: set[tuple[int, int]] = set()

        for pattern, entity_type in _INSTITUTION_PATTERNS:
            for match in re.finditer(pattern, text):
                span = (match.start(1), match.end(1))
                if span in seen:
                    continue
                seen.add(span)
                entities.append(
                    ExtractedEntity(
                        name=match.group(1),
                        entity_type=entity_type,
                        char_start=span[0],
                        char_end=span[1],
                        role="organ_publiczny",
                    )
                )

        for match in _PERSON_PATTERN.finditer(text):
            span = (match.start(), match.end())
            if span in seen:
                continue
            seen.add(span)
            entities.append(
                ExtractedEntity(
                    name=match.group(0),
                    entity_type=EntityType.PERSON,
                    char_start=span[0],
                    char_end=span[1],
                    # Rola procesowa nie wynika z samego wystąpienia nazwiska w tekście.
                    role=None,
                )
            )

        entities.sort(key=lambda e: e.char_start)

        # Relacje wymagają rozstrzygania tożsamości i analizy zdania, nie sąsiedztwa w liście.
        # Poprzednia wersja łączyła pierwszą osobę z pierwszą instytucją krawędzią SUBMITTED_TO
        # niezależnie od treści — to była relacja wymyślona.
        relations: list[EntityRelation] = []

        return NERResponse(entities=entities, relations=relations)
