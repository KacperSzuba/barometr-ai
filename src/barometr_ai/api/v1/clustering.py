"""Semantic stream deduplication and clustering."""

import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends

from barometr_ai.api.dependencies import get_clustering_service
from barometr_ai.domain.models import ClusterRequest, ClusterResponse
from barometr_ai.services.clustering_service import ClusteringService

router = APIRouter(tags=["Clustering"])


@router.post(
    "/cluster", response_model=ClusterResponse, summary="Deduplicate and cluster stream items"
)
async def cluster_documents(
    request: ClusterRequest,
    clustering_service: Annotated[ClusteringService, Depends(get_clustering_service)],
) -> ClusterResponse:
    return await asyncio.to_thread(clustering_service.cluster_documents, request)
