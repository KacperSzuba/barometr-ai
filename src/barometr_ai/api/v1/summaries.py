"""Summarization with strict provenance tracking."""

from fastapi import APIRouter

from barometr_ai.api.dependencies import ClientIdDep, SummarizerDep
from barometr_ai.domain.models import SummarizeRequest, SummarizeResponse

router = APIRouter(tags=["Summarization"])


@router.post(
    "/summarize",
    response_model=SummarizeResponse,
    summary="Generate grounded executive summary with citations",
)
async def summarize_document(
    request: SummarizeRequest,
    summarizer: SummarizerDep,
    client_id: ClientIdDep,
) -> SummarizeResponse:
    return await summarizer.summarize(request, client_id=client_id)
