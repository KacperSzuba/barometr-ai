"""Ekstrakcja encji (NER) i relacji w aktach i materiałach prawnych (F2)."""

import re

from barometr_ai.domain.enterprise_models import (
    EntityRelation,
    EntityType,
    ExtractedEntity,
    NERRequest,
    NERResponse,
)


class EntityExtractorService:
    """Rozpoznaje ministrów, posłów, resorty, instytucje i spółki oraz ich role w procesie."""

    @staticmethod
    def extract_entities(request: NERRequest) -> NERResponse:
        text = request.text
        entities: list[ExtractedEntity] = []
        relations: list[EntityRelation] = []

        # Wzorce dla instytucji i resortów
        inst_patterns = [
            (r"(Ministerstwo\s+[A-ZĄĆĘŁŃÓŚŹŻ][a-ząćęłńóśźż]+(?:\s+[a-ząćęłńóśźż]+)*)", EntityType.INSTITUTION),
            (r"(Sejm\s+Rzeczypospolitej\s+Polskiej|Sejm|Senat)", EntityType.INSTITUTION),
            (r"(Urząd\s+Ochrony\s+Konkurencji\s+i\s+Konsumentów|UOKiK|KNF)", EntityType.INSTITUTION),
            (r"(Naczelny\s+Sąd\s+Administracyjny|Trybunał\s+Konstytucyjny)", EntityType.INSTITUTION),
        ]

        for pat, ent_type in inst_patterns:
            for m in re.finditer(pat, text):
                entities.append(
                    ExtractedEntity(
                        name=m.group(1),
                        entity_type=ent_type,
                        char_start=m.start(),
                        char_end=m.end(),
                        role="organ_publiczny",
                    )
                )

        # Wzorce dla osób publicznych (Ministrowie, Posłowie)
        person_patterns = [
            (r"((?:Minister|Premier|Poseł|Senator|Marszałek)\s+[A-ZĄĆĘŁŃÓŚŹŻ][a-ząćęłńóśźż]+\s+[A-ZĄĆĘŁŃÓŚŹŻ][a-ząćęłńóśźż]+)", "wnioskodawca"),
        ]

        for pat, role in person_patterns:
            for m in re.finditer(pat, text):
                entities.append(
                    ExtractedEntity(
                        name=m.group(1),
                        entity_type=EntityType.PERSON,
                        char_start=m.start(),
                        char_end=m.end(),
                        role=role,
                    )
                )

        # Budowa relacji (jeśli występuje osoba i instytucja)
        person_entities = [e for e in entities if e.entity_type == EntityType.PERSON]
        inst_entities = [e for e in entities if e.entity_type == EntityType.INSTITUTION]

        if person_entities and inst_entities:
            relations.append(
                EntityRelation(
                    source_entity=person_entities[0].name,
                    target_entity=inst_entities[0].name,
                    relation_type="SUBMITTED_TO",
                )
            )

        return NERResponse(entities=entities, relations=relations)