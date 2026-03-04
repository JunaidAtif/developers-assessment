
import uuid
from datetime import datetime, timedelta

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.api.routes.financial.models import (
    Adjustment,
    Remittance,
    TimeSegment,
    WorkLog,
)
from app.core.config import settings
from app.models import User

BASE = f"{settings.API_V1_STR}/financial"

HOURLY_RATE = 30.0


# ---------------------------------------------------------------------------
# Helper seed functions
# ---------------------------------------------------------------------------


def _make_user(db: Session, hourly_rate: float = HOURLY_RATE) -> User:
    """Create a real User row so FK constraints on worklog/time_segment are satisfied."""
    u = User(
        email=f"test-{uuid.uuid4()}@example.com",
        hashed_password="x",
        hourly_rate=hourly_rate,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _set_hourly_rate(db: Session, user_id: uuid.UUID, rate: float) -> None:
    u = db.get(User, user_id)
    if u:
        u.hourly_rate = rate
        db.add(u)
        db.commit()


def _worklog(db: Session, user_id: uuid.UUID, task_name: str = "test-task") -> WorkLog:
    wl = WorkLog(user_id=user_id, task_name=task_name)
    db.add(wl)
    db.commit()
    db.refresh(wl)
    return wl


def _segment(
    db: Session,
    worklog_id: uuid.UUID,
    user_id: uuid.UUID,
    duration_minutes: float,
    status: str = "APPROVED",
) -> TimeSegment:
    now = datetime.utcnow()
    seg = TimeSegment(
        worklog_id=worklog_id,
        user_id=user_id,
        start_time=now - timedelta(minutes=duration_minutes),
        end_time=now,
        duration_minutes=duration_minutes,
        status=status,
    )
    db.add(seg)
    db.commit()
    db.refresh(seg)
    return seg


def _adjustment(
    db: Session,
    user_id: uuid.UUID,
    amount: float,
    status: str = "APPROVED",
    reason: str = "test adjustment",
) -> Adjustment:
    adj = Adjustment(user_id=user_id, amount=amount, reason=reason, status=status)
    db.add(adj)
    db.commit()
    db.refresh(adj)
    return adj


# ---------------------------------------------------------------------------
# Test: generate-remittances-for-all-users
# ---------------------------------------------------------------------------


def test_generate_remittances_empty(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    """Returns 201 with empty list when there is nothing to settle."""
    response = client.post(
        f"{BASE}/generate-remittances-for-all-users",
        headers=superuser_token_headers,
    )
    assert response.status_code == 201
    body = response.json()
    assert "data" in body
    assert "count" in body
    assert isinstance(body["data"], list)


def test_generate_remittances_response_shape(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    """Response has data list and integer count."""
    response = client.post(
        f"{BASE}/generate-remittances-for-all-users",
        headers=superuser_token_headers,
    )
    assert response.status_code == 201
    body = response.json()
    assert isinstance(body["data"], list)
    assert isinstance(body["count"], int)
    assert body["count"] == len(body["data"])


def test_generate_remittances_creates_success_remittance(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    """
    A worklog with APPROVED segments produces one SUCCESS remittance.
    total_amount = duration_minutes / 60 * hourly_rate
    120 min / 60 * 30 = 60.0
    """
    u = _make_user(db)
    wl = _worklog(db, u.id, "test-generate-creates")
    _segment(db, wl.id, u.id, duration_minutes=120.0)

    response = client.post(
        f"{BASE}/generate-remittances-for-all-users",
        headers=superuser_token_headers,
    )
    assert response.status_code == 201
    body = response.json()
    user_rems = [r for r in body["data"] if r["user_id"] == str(u.id)]
    assert len(user_rems) == 1
    r = user_rems[0]
    assert r["status"] == "SUCCESS"
    assert r["total_amount"] == 60.0
    assert "period_start" in r
    assert "period_end" in r


def test_generate_remittances_idempotent(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    """
    Running settlement twice: first run returns a remittance,
    second run returns empty (nothing outstanding). Rule 2.
    """
    u = _make_user(db)
    wl = _worklog(db, u.id, "test-idempotent")
    _segment(db, wl.id, u.id, duration_minutes=60.0)

    r1 = client.post(
        f"{BASE}/generate-remittances-for-all-users",
        headers=superuser_token_headers,
    )
    assert r1.status_code == 201
    assert any(r["user_id"] == str(u.id) for r in r1.json()["data"])

    r2 = client.post(
        f"{BASE}/generate-remittances-for-all-users",
        headers=superuser_token_headers,
    )
    assert r2.status_code == 201
    # No new remittance for this user on the second run
    user_rems = [r for r in r2.json()["data"] if r["user_id"] == str(u.id)]
    assert len(user_rems) == 0


def test_generate_remittances_excludes_pending_segments(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    """PENDING segments are not eligible. Rule 1."""
    u = _make_user(db)
    wl = _worklog(db, u.id, "test-pending-excluded")
    _segment(db, wl.id, u.id, duration_minutes=120.0, status="PENDING")

    response = client.post(
        f"{BASE}/generate-remittances-for-all-users",
        headers=superuser_token_headers,
    )
    assert response.status_code == 201
    user_rems = [r for r in response.json()["data"] if r["user_id"] == str(u.id)]
    assert len(user_rems) == 0


def test_generate_remittances_excludes_declined_segments(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    """DECLINED segments are not eligible. Rule 1."""
    u = _make_user(db)
    wl = _worklog(db, u.id, "test-declined-excluded")
    _segment(db, wl.id, u.id, duration_minutes=120.0, status="DECLINED")

    response = client.post(
        f"{BASE}/generate-remittances-for-all-users",
        headers=superuser_token_headers,
    )
    assert response.status_code == 201
    user_rems = [r for r in response.json()["data"] if r["user_id"] == str(u.id)]
    assert len(user_rems) == 0


def test_generate_remittances_includes_adjustment(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    """
    APPROVED adjustments are added to the remittance total. Rule 4.
    60 min segment = 30.0 + 15.0 adjustment = 45.0
    """
    u = _make_user(db)
    wl = _worklog(db, u.id, "test-adjustment-included")
    _segment(db, wl.id, u.id, duration_minutes=60.0)
    _adjustment(db, u.id, amount=15.0)

    response = client.post(
        f"{BASE}/generate-remittances-for-all-users",
        headers=superuser_token_headers,
    )
    assert response.status_code == 201
    user_rems = [r for r in response.json()["data"] if r["user_id"] == str(u.id)]
    assert len(user_rems) == 1
    assert user_rems[0]["total_amount"] == 45.0


def test_generate_remittances_adjustment_marked_consumed(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    """
    After settlement the adjustment status is CONSUMED, not DECLINED.
    Audit trail is preserved. Rule 4.
    """
    u = _make_user(db)
    wl = _worklog(db, u.id, "test-adjustment-consumed")
    _segment(db, wl.id, u.id, duration_minutes=60.0)
    adj = _adjustment(db, u.id, amount=10.0)

    client.post(
        f"{BASE}/generate-remittances-for-all-users",
        headers=superuser_token_headers,
    )

    db.refresh(adj)
    assert adj.status == "CONSUMED"
    assert adj.amount == 10.0
    assert adj.reason == "test adjustment"


def test_generate_remittances_new_segment_after_settlement(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    """
    New APPROVED segment added after a settled worklog is included in the
    next remittance run. Previously settled segments are NOT re-included. Rule 3.
    """
    u = _make_user(db)
    wl = _worklog(db, u.id, "test-rule3-new-segment")
    _segment(db, wl.id, u.id, duration_minutes=60.0)  # 30.0

    r1 = client.post(
        f"{BASE}/generate-remittances-for-all-users",
        headers=superuser_token_headers,
    )
    assert r1.status_code == 201
    first = [r for r in r1.json()["data"] if r["user_id"] == str(u.id)]
    assert first[0]["total_amount"] == 30.0

    # Add new segment after settlement
    _segment(db, wl.id, u.id, duration_minutes=120.0)  # 60.0

    r2 = client.post(
        f"{BASE}/generate-remittances-for-all-users",
        headers=superuser_token_headers,
    )
    assert r2.status_code == 201
    second = [r for r in r2.json()["data"] if r["user_id"] == str(u.id)]
    assert len(second) == 1
    assert second[0]["total_amount"] == 60.0


def test_generate_remittances_failed_does_not_block_retry(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    """
    A FAILED remittance in the ledger must not prevent a new SUCCESS
    remittance from being issued for the same segments. Rule 5.
    """
    u = _make_user(db)
    wl = _worklog(db, u.id, "test-rule5-failed-retry")
    _segment(db, wl.id, u.id, duration_minutes=60.0)

    # Simulate a prior FAILED remittance
    failed = Remittance(
        user_id=u.id,
        period_start=datetime(2026, 3, 1),
        period_end=datetime.utcnow(),
        total_amount=30.0,
        status="FAILED",
    )
    db.add(failed)
    db.commit()

    response = client.post(
        f"{BASE}/generate-remittances-for-all-users",
        headers=superuser_token_headers,
    )
    assert response.status_code == 201
    paid = [
        r for r in response.json()["data"]
        if r["user_id"] == str(u.id) and r["status"] == "SUCCESS"
    ]
    assert len(paid) == 1
    assert paid[0]["total_amount"] == 30.0


# ---------------------------------------------------------------------------
# Test: list-all-worklogs
# ---------------------------------------------------------------------------


def test_list_worklogs_returns_200(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    """GET /list-all-worklogs returns 200 with data and count."""
    u = _make_user(db)
    _worklog(db, u.id)
    response = client.get(
        f"{BASE}/list-all-worklogs",
        headers=superuser_token_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert "data" in body
    assert "count" in body


def test_list_worklogs_response_fields(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    """Each worklog entry has all required fields."""
    u = _make_user(db)
    wl = _worklog(db, u.id, "test-fields")
    _segment(db, wl.id, u.id, duration_minutes=60.0)

    response = client.get(f"{BASE}/list-all-worklogs", headers=superuser_token_headers)
    assert response.status_code == 200
    entry = next(w for w in response.json()["data"] if w["id"] == str(wl.id))
    for field in (
        "id",
        "user_id",
        "task_name",
        "total_amount",
        "settled_amount",
        "outstanding_amount",
        "created_at",
    ):
        assert field in entry, f"Missing field: {field}"


def test_list_worklogs_amounts_before_settlement(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    """
    Before settlement: total_amount > 0, settled_amount = 0,
    outstanding_amount = total_amount.
    120 min / 60 * 30 = 60.0
    """
    u = _make_user(db)
    wl = _worklog(db, u.id, "test-amounts-before")
    _segment(db, wl.id, u.id, duration_minutes=120.0)

    response = client.get(f"{BASE}/list-all-worklogs", headers=superuser_token_headers)
    entry = next(w for w in response.json()["data"] if w["id"] == str(wl.id))
    assert entry["total_amount"] == 60.0
    assert entry["settled_amount"] == 0.0
    assert entry["outstanding_amount"] == 60.0


def test_list_worklogs_amounts_after_settlement(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    """
    After settlement: settled_amount = total_amount, outstanding_amount = 0.
    """
    u = _make_user(db)
    wl = _worklog(db, u.id, "test-amounts-after")
    _segment(db, wl.id, u.id, duration_minutes=120.0)

    client.post(
        f"{BASE}/generate-remittances-for-all-users",
        headers=superuser_token_headers,
    )

    response = client.get(f"{BASE}/list-all-worklogs", headers=superuser_token_headers)
    entry = next(w for w in response.json()["data"] if w["id"] == str(wl.id))
    assert entry["total_amount"] == 60.0
    assert entry["settled_amount"] == 60.0
    assert entry["outstanding_amount"] == 0.0


def test_list_worklogs_filter_unremitted(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    """UNREMITTED filter: every returned worklog has outstanding_amount > 0."""
    u = _make_user(db)
    wl = _worklog(db, u.id, "test-filter-unremitted")
    _segment(db, wl.id, u.id, duration_minutes=60.0)

    response = client.get(
        f"{BASE}/list-all-worklogs",
        headers=superuser_token_headers,
        params={"remittanceStatus": "UNREMITTED"},
    )
    assert response.status_code == 200
    # The worklog we just created must appear and have outstanding balance
    wl_entries = [e for e in response.json()["data"] if e["id"] == str(wl.id)]
    assert len(wl_entries) == 1
    assert wl_entries[0]["outstanding_amount"] > 0


def test_list_worklogs_filter_remitted(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    """REMITTED filter: the settled worklog appears with outstanding_amount = 0."""
    u = _make_user(db)
    wl = _worklog(db, u.id, "test-filter-remitted")
    _segment(db, wl.id, u.id, duration_minutes=60.0)

    client.post(
        f"{BASE}/generate-remittances-for-all-users",
        headers=superuser_token_headers,
    )

    response = client.get(
        f"{BASE}/list-all-worklogs",
        headers=superuser_token_headers,
        params={"remittanceStatus": "REMITTED"},
    )
    assert response.status_code == 200
    wl_entries = [w for w in response.json()["data"] if w["id"] == str(wl.id)]
    assert len(wl_entries) == 1
    assert wl_entries[0]["outstanding_amount"] == 0.0
    assert wl_entries[0]["settled_amount"] > 0


def test_list_worklogs_invalid_filter(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    """Invalid remittanceStatus returns 400."""
    response = client.get(
        f"{BASE}/list-all-worklogs",
        headers=superuser_token_headers,
        params={"remittanceStatus": "INVALID"},
    )
    assert response.status_code == 400
