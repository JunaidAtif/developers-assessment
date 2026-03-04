"""
Financial domain API router.

Endpoints:
  POST /financial/generate-remittances-for-all-users
  GET  /financial/list-all-worklogs
"""

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.api.deps import CurrentUser, SessionDep
from app.api.routes.financial import service as financial_service
from app.api.routes.financial.schemas import (
    RemittancesPublic,
    WorkLogsPublic,
)

router = APIRouter(prefix="/financial", tags=["financial"])


# ---------------------------------------------------------------------------
# Generate Remittances
# ---------------------------------------------------------------------------


@router.post(
    "/generate-remittances-for-all-users",
    response_model=RemittancesPublic,
    status_code=201,
)
def generate_remittances_for_all_users(
    session: SessionDep,
    current_user: CurrentUser,  # noqa: ARG001
) -> Any:
    """
    Run a settlement pass for all users.

    For each user with outstanding work:
      1. Collect APPROVED segments not yet in a SUCCESS remittance_item
      2. Collect unconsumed APPROVED adjustments
      3. Record the remittance: PENDING → PROCESSING → SUCCESS
         (or FAILED if anything goes wrong — ledger entry preserved either way)

    Idempotent: re-running when nothing is outstanding returns empty list.
    """
    return financial_service.generate_remittances(session)


# ---------------------------------------------------------------------------
# List WorkLogs
# ---------------------------------------------------------------------------


@router.get(
    "/list-all-worklogs",
    response_model=WorkLogsPublic,
)
def list_all_worklogs(
    session: SessionDep,
    current_user: CurrentUser,  # noqa: ARG001
    remittanceStatus: str | None = Query(
        default=None,
        description="Filter by remittance status. Accepts REMITTED or UNREMITTED.",
    ),
) -> Any:
    """
    List all worklogs with computed financial information.

    amount per worklog = SUM(duration_minutes / 60 * user.hourly_rate)
    for APPROVED segments.

    REMITTED   → ALL approved segments already in a SUCCESS remittance_item
    UNREMITTED → at least one approved segment not yet remitted
    """
    status_filter: str | None = None

    if remittanceStatus:
        value = remittanceStatus.strip().upper()

        if value not in ("REMITTED", "UNREMITTED"):
            raise HTTPException(
                status_code=400,
                detail="remittanceStatus must be REMITTED or UNREMITTED",
            )

        status_filter = value

    return financial_service.list_worklogs(session, status_filter)
