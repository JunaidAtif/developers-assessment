import uuid
from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel


# =========================
# WORK LOGS
# =========================

class WorkLog(SQLModel, table=True):
    """
    Task container. Does NOT store any amount.
    Amount is derived from its time_segments at query time.
    """

    __tablename__ = "worklog"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="user.id", index=True, nullable=False)
    task_name: str = Field(index=True, nullable=False)

    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)


# =========================
# TIME SEGMENTS
# =========================

class TimeSegment(SQLModel, table=True):
    """
    Core mutable unit of reported work.
    Duration can change and status can change.
    Financial correctness is preserved via remittance_item snapshots —
    NOT by locking this row.
    """

    __tablename__ = "time_segment"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    worklog_id: uuid.UUID = Field(foreign_key="worklog.id", index=True, nullable=False)
    user_id: uuid.UUID = Field(foreign_key="user.id", index=True, nullable=False)

    start_time: datetime = Field(nullable=False)
    end_time: datetime = Field(nullable=False)

    # Computed and stored for convenience; re-derived when needed
    duration_minutes: float = Field(nullable=False)

    # PENDING | APPROVED | DECLINED
    status: str = Field(default="PENDING", index=True)

    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


# =========================
# REMITTANCES
# =========================

class Remittance(SQLModel, table=True):
    """
    One monthly payout attempt for a single user.
    Only SUCCESS status means money was actually paid.
    FAILED/CANCELLED are inert audit records.
    """

    __tablename__ = "remittance"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="user.id", index=True, nullable=False)

    period_start: datetime = Field(nullable=False, index=True)
    period_end: datetime = Field(nullable=False, index=True)

    total_amount: float = Field(nullable=False)

    # PENDING | PROCESSING | SUCCESS | FAILED | CANCELLED
    status: str = Field(default="PENDING", index=True)

    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)


# =========================
# REMITTANCE ITEMS (CRITICAL)
# =========================

class RemittanceItem(SQLModel, table=True):
    """
    Links individual time_segments to a remittance.
    - Prevents double payment (a segment appears here only once across SUCCESS remittances)
    - Tracks exactly what was included in each payout
    - Freezes the amount at time of settlement
    """

    __tablename__ = "remittance_item"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)

    remittance_id: uuid.UUID = Field(foreign_key="remittance.id", index=True, nullable=False)
    time_segment_id: uuid.UUID = Field(foreign_key="time_segment.id", index=True, nullable=False)

    # Amount frozen at time of settlement: duration_minutes / 60 * user.hourly_rate
    amount: float = Field(nullable=False)

    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)


# =========================
# ADJUSTMENTS
# =========================

class Adjustment(SQLModel, table=True):
    """
    Retroactive correction to worker pay.
    Can be positive (bonus) or negative (deduction).
    Linked optionally to a specific time_segment or worklog.
    Gets included in the NEXT remittance — old remittances are never modified.
    """

    __tablename__ = "adjustment"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)

    user_id: uuid.UUID = Field(foreign_key="user.id", index=True, nullable=False)
    time_segment_id: Optional[uuid.UUID] = Field(
        default=None, foreign_key="time_segment.id", index=True, nullable=True
    )
    worklog_id: Optional[uuid.UUID] = Field(
        default=None, foreign_key="worklog.id", index=True, nullable=True
    )

    # Positive = bonus, negative = deduction
    amount: float = Field(nullable=False)
    reason: str = Field(nullable=False)

    # PENDING | APPROVED | DECLINED
    status: str = Field(default="PENDING", index=True)

    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)