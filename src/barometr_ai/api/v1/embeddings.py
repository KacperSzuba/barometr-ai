"""Vector embedding endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends

from barometr_ai.api.dependencies import get_embedder
from barometr_ai.core.config import Settings, get_settings
from barometr_ai.domain.models import EmbedRequest, EmbedResponse
from barometr_ai.ports.embedder import EmbedderPort

router = APIRouter(tags=["Embeddings"])


@router.post("/embed", response_model=EmbedResponse, summary="Generate vector embeddings for texts")
async def generate_embeddings(
    request: EmbedRequest,
    embedder: Annotated[EmbedderPort, Depends(get_embedder)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> EmbedResponse:
    vectors = embedder.embed_texts(request.texts, normalize=request.normalize)

    return EmbedResponse(
        embeddings=vectors,
        model_version=embedder.model_name,
        dimension=embedder.dimension,
        count=len(vectors),
    )