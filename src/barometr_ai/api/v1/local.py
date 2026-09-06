"""Endpoint parsera dokumentów BIP samorządu (F4 Local)."""

import asyncio

from fastapi import APIRouter

from barometr_ai.domain.enterprise_models import LocalParseRequest, LocalParseResponse
from barometr_ai.services.local_parser_service import LocalDocumentParserService

router = APIRouter(tags=["Local"])


@router.post(
    "/local/parse", response_model=LocalParseResponse, summary="Parsuj uchwałę/budżet/MPZP z BIP"
)
async def parse_local_document(request: LocalParseRequest) -> LocalParseResponse:
    # Dokument BIP bywa wielostronicowy, a parser przechodzi go w całości.
    return await asyncio.to_thread(LocalDocumentParserService.parse_document, request)
