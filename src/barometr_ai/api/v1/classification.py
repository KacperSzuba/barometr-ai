"""Document classification endpoints."""

import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends

from barometr_ai.api.dependencies import get_classifier_service
from barometr_ai.domain.models import ClassifyRequest, ClassifyResponse
from barometr_ai.services.classifier_service import ClassifierService

router = APIRouter(tags=["Classification"])


@router.post(
    "/classify", response_model=ClassifyResponse, summary="Classify document by PKD and legal topic"
)
async def classify_document(
    request: ClassifyRequest,
    classifier: Annotated[ClassifierService, Depends(get_classifier_service)],
) -> ClassifyResponse:
    return await asyncio.to_thread(classifier.classify, request.title, request.content)
