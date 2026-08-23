"""Vector embedding endpoints."""

import asyncio

from fastapi import APIRouter

from barometr_ai.api.dependencies import EmbedderDep
from barometr_ai.domain.models import EmbedRequest, EmbedResponse

router = APIRouter(tags=["Embeddings"])


@router.post("/embed", response_model=EmbedResponse, summary="Generate vector embeddings for texts")
async def generate_embeddings(request: EmbedRequest, embedder: EmbedderDep) -> EmbedResponse:
    # Inferencja ONNX jest CPU-bound. Bez przeniesienia do puli wątków blokowałaby pętlę
    # zdarzeń na czas całej paczki — wymóg AGENTS.md §2.5.
    vectors = await asyncio.to_thread(
        embedder.embed_texts,
        request.texts,
        request.normalize,
        input_type=request.input_type,
    )

    return EmbedResponse(
        embeddings=vectors,
        model_version=embedder.model_version,
        model_name=embedder.model_name,
        dimension=embedder.dimension,
        count=len(vectors),
    )
