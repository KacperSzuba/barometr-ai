"""Rozliczenie zużycia tokenów per klient (F1).

Licznik budżetu jest jedynym stanem, jaki serwis utrzymuje między żądaniami, i do tej pory
nie miał jak wyjść na zewnątrz: `X-Client-Id` był przyjmowany i doliczany, ale odczytać go
mógł tylko test. Ten endpoint go udostępnia — nic nie liczy od nowa, tylko czyta magazyn.
"""

from fastapi import APIRouter

from barometr_ai.api.dependencies import ClientIdDep, CostTrackerDep, SettingsDep
from barometr_ai.domain.models import UsageResponse

router = APIRouter(tags=["Usage"])


@router.get(
    "/usage",
    response_model=UsageResponse,
    summary="Zużycie tokenów klienta i stan dziennego budżetu",
)
async def read_usage(
    client_id: ClientIdDep,
    cost_tracker: CostTrackerDep,
    settings: SettingsDep,
) -> UsageResponse:
    service_tokens = cost_tracker.tokens_today
    return UsageResponse(
        client_id=client_id,
        client_tokens_today=cost_tracker.usage_for_client(client_id),
        service_tokens_today=service_tokens,
        daily_budget=cost_tracker.daily_budget,
        usage_ratio=round(service_tokens / cost_tracker.daily_budget, 3),
        alert_threshold=cost_tracker.alert_threshold,
        alert_active=service_tokens / cost_tracker.daily_budget >= cost_tracker.alert_threshold,
        budget_scope="shared" if settings.token_budget_backend == "redis" else "process",
    )
