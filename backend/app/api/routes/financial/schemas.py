"""
Financial domain Pydantic schemas (request / response models).
"""

import uuid
from datetime import datetime

from pydantic import BaseModel

# ---------------------------------------------------------------------------
# WorkLog schemas
# ---------------------------------------------------------------------------


class WorkLogPublic(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    task_name: str
    total_amount: float
    settled_amount: float
    outstanding_amount: float
    created_at: datetime

    model_config = {"from_attributes": True}


class WorkLogsPublic(BaseModel):
    data: list[WorkLogPublic]
    count: int


# ---------------------------------------------------------------------------
# Remittance schemas
# ---------------------------------------------------------------------------


class RemittancePublic(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    period_start: datetime
    period_end: datetime
    total_amount: float
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class RemittancesPublic(BaseModel):
    data: list[RemittancePublic]
    count: int
