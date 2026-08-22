"""Endpoint ekstrakcji encji NER i relacji (F2)."""

from fastapi import APIRouter

from barometr_ai.domain.enterprise_models import NERRequest, NERResponse
from barometr_ai.services.entity_extractor import EntityExtractorService

router = APIRouter(tags=["NER"])


@router.post("/ner", response_model=NERResponse, summary="Wyodrębnij osoby, instytucje i relacje")
async def extract_entities(request: NERRequest) -> NERResponse:
    return EntityExtractorService.extract_entities(request)