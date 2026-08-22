"""Drzewiasty diff wersji prawnych i korelacja ze zgłoszeniami RCL (F3)."""

from fastapi import APIRouter

from barometr_ai.domain.advanced_models import LegalDiffRequest, LegalDiffResponse
from barometr_ai.services.legal_diff_service import LegalDiffService

router = APIRouter(tags=["Diff"])


@router.post("/diff", response_model=LegalDiffResponse, summary="Porównaj wersje projektu i powiąż z uwagami RCL")
async def compare_versions(request: LegalDiffRequest) -> LegalDiffResponse:
    return LegalDiffService.compare_and_correlate(request)