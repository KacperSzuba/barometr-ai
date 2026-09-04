"""Orkiestrator kaskady kosztowej — jedno przejście L1 → L2 → L3 nad wsadem dokumentów."""

from typing import Annotated

from fastapi import APIRouter, Depends

from barometr_ai.api.dependencies import ClientIdDep, get_cascade_service
from barometr_ai.domain.pipeline_models import PipelineRequest, PipelineResponse
from barometr_ai.services.cascade_service import CascadeService

router = APIRouter(tags=["Pipeline"])


@router.post(
    "/pipeline",
    response_model=PipelineResponse,
    summary="Kaskada: klastrowanie → istotność → top-N → streszczenia",
    description=(
        "Przepuszcza wsad dokumentów przez wszystkie trzy warstwy w jednym żądaniu. "
        "Model językowy widzi wyłącznie reprezentantów top-N klastrów, które przeszły próg "
        "istotności i zmieściły się w dziennym budżecie tokenów. Klastry pominięte wracają "
        "w odpowiedzi z jawnym `skip_reason` — żaden dokument nie znika po cichu."
    ),
)
async def run_pipeline(
    request: PipelineRequest,
    cascade: Annotated[CascadeService, Depends(get_cascade_service)],
    client_id: ClientIdDep,
) -> PipelineResponse:
    return await cascade.run(request, client_id=client_id)
