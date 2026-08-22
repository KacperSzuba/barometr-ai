"""Summarization with strict provenance tracking."""

from typing import Annotated

from fastapi import APIRouter, Depends

from barometr_ai.api.dependencies import get_summarizer_service
from barometr_ai.domain.models import SummarizeRequest, SummarizeResponse
from barometr_ai.services.summarizer_service import SummarizerService

router = APIRouter(tags=["Summarization"])


@router.post("/summarize", response_model=SummarizeResponse, summary="Generate grounded executive summary with citations")
async def summarize_document(
    request: SummarizeRequest,
    summarizer: Annotated[SummarizerService, Depends(get_summarizer_service)],
) -> SummarizeResponse:
    return summarizer.summarize(request)