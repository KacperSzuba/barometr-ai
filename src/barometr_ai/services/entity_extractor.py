"""Ekstrakcja encji (NER) i relacji w aktach i materiałach prawnych (F2)."""

import re

from barometr_ai.domain.enterprise_models import (
    EntityRelation,
    EntityType,
    ExtractedEntity,
    NERRequest,
    NERResponse,
    RelationType,
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


#: Konstrukcje czasownikowe, z których relacja *wynika wprost*. Lista jest celowo wąska:
#: wzorzec, który trzeba interpretować, wpuszczałby z powrotem relacje zgadywane. Każdy
#: wzorzec musi wskazywać kierunek (podmiot przed czasownikiem, cel po nim).
_RELATION_PATTERNS: list[tuple[re.Pattern[str], RelationType]] = [
    (
        re.compile(
            r"\b(?:złoż(?:ył|yła|yli)|skierowa(?:ł|ła|li)|wni(?:ósł|osła|eśli)|"
            r"przekaza(?:ł|ła|li))\b[^.!?]{0,80}?\bdo\b",
            re.IGNORECASE,
        ),
        RelationType.SUBMITTED,
    ),
    (
        re.compile(
            r"\b(?:zgłosi(?:ł|ła|li)\s+poprawk[ęi]|znowelizowa(?:ł|ła|li)|"
            r"wprowadzi(?:ł|ła|li)\s+zmian[yę])\b[^.!?]{0,80}?\b(?:do|w)\b",
            re.IGNORECASE,
        ),
        RelationType.AMENDED,
    ),
    (
        re.compile(
            r"\b(?:nadzoruje|sprawuje\s+nadzór\s+nad|reguluje|kontroluje)\b",
            re.IGNORECASE,
        ),
        RelationType.REGULATES,
    ),
    (
        re.compile(
            r"\b(?:sprzeciwi(?:ł|ła|li)\s+się|zgłosi(?:ł|ła|li)\s+sprzeciw\s+wobec|"
            r"zaoponowa(?:ł|ła|li)\s+wobec)\b",
            re.IGNORECASE,
        ),
        RelationType.OPPOSES,
    ),
    (
        re.compile(
            r"\b(?:powiadomi(?:ł|ła|li)|poinformowa(?:ł|ła|li)|zawiadomi(?:ł|ła|li))\b",
            re.IGNORECASE,
        ),
        RelationType.NOTIFIED,
    ),
]

#: Granica zdania. Relacja nigdy nie przekracza zdania — encje z dwóch różnych zdań łączy
#: co najwyżej sąsiedztwo, a to była właśnie odrzucona heurystyka.
_SENTENCE_BOUNDARY = re.compile(r"[.!?]+\s+")

#: Encja musi przylegać do konstrukcji czasownikowej — między nią a czasownikiem wolno stać
#: wyłącznie białym znakom. Każde słowo w tej szczelinie oznacza, że zdanie ma strukturę,
#: której ten serwis nie analizuje:
#:
#: - „Nowak złożył wniosek do Sejmu **oraz** powiadomił UOKiK" — podmiotem powiadomienia jest
#:   Nowak (podmiot współdzielony), a nie sąsiadujący Sejm;
#: - „zgłosił poprawkę do **projektu, a** Minister Lis…" — encja po czasowniku należy już do
#:   następnego zdania składowego, nie jest celem poprawki.
#:
#: Rozstrzygnięcie obu wymaga analizy składniowej, więc zamiast zgadywać nie zwracamy relacji.
#: Tracimy krawędzie prawdziwe, ale nie dodajemy fałszywych — w produkcie, którego obietnicą
#: jest weryfikowalność, to jest właściwy kierunek wymiany.
_ADJACENT = re.compile(r"\A\s*\Z")


class EntityExtractorService:
    """Rozpoznaje ministrów, posłów, resorty i instytucje w tekście.

    Świadome ograniczenie: to ekstrakcja wzorcami, nie NER. Nie rozstrzyga tożsamości
    ("min. Nowak" nie jest łączone z "Minister Adam Nowak") i nie wyznacza ról procesowych.
    Zadanie F2 wymaga modelu NER dla polskiego i słowników instytucji.

    Relacje pochodzą wyłącznie z jawnej konstrukcji czasownikowej między dwiema encjami
    w obrębie jednego zdania i niosą offsety fragmentu, z którego wynikają. Zdanie bez
    takiej konstrukcji nie daje relacji — brak krawędzi jest uczciwszy niż krawędź
    wyprowadzona z kolejności encji na liście, którą serwis zwracał wcześniej.
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

        return NERResponse(
            entities=entities,
            relations=EntityExtractorService._extract_relations(text, entities),
        )

    @staticmethod
    def _sentence_spans(text: str) -> list[tuple[int, int]]:
        """Dzieli tekst na zdania, zachowując offsety względem oryginału."""
        spans: list[tuple[int, int]] = []
        start = 0
        for boundary in _SENTENCE_BOUNDARY.finditer(text):
            spans.append((start, boundary.start()))
            start = boundary.end()
        if start < len(text):
            spans.append((start, len(text)))
        return spans

    @staticmethod
    def _extract_relations(text: str, entities: list[ExtractedEntity]) -> list[EntityRelation]:
        """Łączy encje tylko tam, gdzie zdanie niesie jawną konstrukcję czasownikową.

        Kierunek relacji bierze się z szyku: podmiotem jest ostatnia encja kończąca się przed
        czasownikiem, celem — pierwsza zaczynająca się po nim. Jeżeli po którejś stronie nie ma
        encji, relacja nie powstaje.
        """
        relations: list[EntityRelation] = []

        for sentence_start, sentence_end in EntityExtractorService._sentence_spans(text):
            in_sentence = [
                entity
                for entity in entities
                if entity.char_start >= sentence_start and entity.char_end <= sentence_end
            ]
            if len(in_sentence) < 2:
                continue

            sentence = text[sentence_start:sentence_end]

            for pattern, relation_type in _RELATION_PATTERNS:
                for match in pattern.finditer(sentence):
                    trigger_start = sentence_start + match.start()
                    trigger_end = sentence_start + match.end()

                    before = [e for e in in_sentence if e.char_end <= trigger_start]
                    after = [e for e in in_sentence if e.char_start >= trigger_end]
                    if not before or not after:
                        continue

                    source = before[-1]
                    target = after[0]

                    if not _ADJACENT.match(text[source.char_end : trigger_start]):
                        continue
                    if not _ADJACENT.match(text[trigger_end : target.char_start]):
                        continue
                    relations.append(
                        EntityRelation(
                            source_entity=source.name,
                            target_entity=target.name,
                            relation_type=relation_type,
                            char_start=source.char_start,
                            char_end=target.char_end,
                            trigger=text[trigger_start:trigger_end],
                        )
                    )

        relations.sort(key=lambda r: (r.char_start, r.char_end))
        return relations
