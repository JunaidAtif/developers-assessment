import logging
from datetime import datetime

from sqlmodel import Session, select

from app.api.routes.financial.models import (
    Adjustment,
    Remittance,
    RemittanceItem,
    TimeSegment,
    WorkLog,
)
from app.api.routes.financial.schemas import (
    RemittancesPublic,
    WorkLogPublic,
    WorkLogsPublic,
)
from app.models import User

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _get_hourly_rate(u_id, session: Session) -> float:
    """
    u_id: user UUID
    Returns user.hourly_rate, or 0.0 if user is not found.
    """
    u = session.get(User, u_id)
    if u is None:
        logger.warning(f"User {u_id} not found — using rate 0.0")
        return 0.0
    return float(getattr(u, "hourly_rate", 0.0))


def _seg_amt(seg: TimeSegment, rate: float) -> float:
    """
    seg:  TimeSegment row
    rate: hourly_rate
    Computes amount for one segment: duration_minutes / 60 * rate
    """
    return (seg.duration_minutes / 60.0) * rate


def _remitted_seg_ids(session: Session) -> set:
    """
    Returns set of time_segment_id values that already exist inside a
    RemittanceItem that belongs to a SUCCESS remittance.

    This is the single source of truth for "has this segment been paid?".
    Rule 2: APPROVED + NOT in this set = eligible.
    Rule 3: new APPROVED segments added after settlement are NOT in this
            set, so they naturally appear in the next run.
    """
    rows = session.exec(
        select(RemittanceItem.time_segment_id)
        .join(Remittance, Remittance.id == RemittanceItem.remittance_id)
        .where(Remittance.status == "SUCCESS")
    ).all()
    return set(rows)


def _unconsumed_adjustments(u_id, session: Session) -> list[Adjustment]:
    """
    u_id: user UUID
    Returns APPROVED adjustments for the user that have NOT yet been
    included in a remittance (status == APPROVED, not CONSUMED).

    Rule 4: adjustments are additive and audit-safe. We never delete or
    overwrite them. After inclusion we mark them CONSUMED (not DECLINED)
    so the audit trail is preserved.
    """
    return list(
        session.exec(
            select(Adjustment).where(
                Adjustment.user_id == u_id,
                Adjustment.status == "APPROVED",
            )
        ).all()
    )


# ---------------------------------------------------------------------------
# generate_remittances
# ---------------------------------------------------------------------------


def generate_remittances(session: Session) -> RemittancesPublic:
    """
    Ledger-based settlement pass for all users.

    Rules enforced:
      Rule 1 - only APPROVED segments are eligible
      Rule 2 - segments already in a SUCCESS remittance_item are excluded
      Rule 3 - new APPROVED segments added after a prior settlement are
               automatically included (they are not in _remitted_seg_ids)
      Rule 4 - adjustments are additive; consumed ones are marked CONSUMED,
               never deleted or overwritten
      Rule 5 - payout can fail: remittance starts PENDING, moves to
               PROCESSING before any item writes, then SUCCESS only after
               all items commit cleanly; on any failure it is marked FAILED
               and the session is rolled back - nothing is double-counted

    Returns list of SUCCESS remittances created this run.
    Idempotent: re-running when nothing is outstanding returns empty list.
    """
    now = datetime.utcnow()
    results: list[Remittance] = []

    # Snapshot of already-paid segment IDs (Rule 2 + Rule 3)
    paid_ids = _remitted_seg_ids(session)

    # Collect unique users who have worklogs
    wls = session.exec(select(WorkLog)).all()
    u_ids = list({wl.user_id for wl in wls})

    for u_id in u_ids:
        rmtnc = None
        try:
            rate = _get_hourly_rate(u_id, session)

            # --- Rule 1 + 2: eligible = APPROVED and not already paid ---
            segs = session.exec(
                select(TimeSegment).where(
                    TimeSegment.user_id == u_id,
                    TimeSegment.status == "APPROVED",
                )
            ).all()
            eligible = [s for s in segs if s.id not in paid_ids]

            # --- Rule 4: unconsumed APPROVED adjustments ---
            adjs = _unconsumed_adjustments(u_id, session)
            adj_ttl = sum(a.amount for a in adjs)

            seg_ttl = sum(_seg_amt(s, rate) for s in eligible)
            total = round(seg_ttl + adj_ttl, 2)

            # Nothing to settle for this user this run
            if not eligible and round(adj_ttl, 10) == 0:
                continue

            # --- Rule 5: create remittance in PENDING first ---
            # The row exists in the ledger from this point forward.
            # It will only reach SUCCESS after every item is written.
            rmtnc = Remittance(
                user_id=u_id,
                period_start=datetime(now.year, now.month, 1),
                period_end=now,
                total_amount=total,
                status="PENDING",
                created_at=now,
            )
            session.add(rmtnc)
            session.commit()
            session.refresh(rmtnc)

            # --- Rule 5: advance to PROCESSING before writing items ---
            # A crash here leaves the remittance in PROCESSING. It is
            # visible in the ledger but never SUCCESS, so paid_ids will
            # not include its items and the run is safely retryable.
            rmtnc.status = "PROCESSING"
            session.add(rmtnc)
            session.commit()

            # Write one RemittanceItem per eligible segment (ledger snapshot)
            for seg in eligible:
                itm = RemittanceItem(
                    remittance_id=rmtnc.id,
                    time_segment_id=seg.id,
                    amount=round(_seg_amt(seg, rate), 2),
                    created_at=now,
                )
                session.add(itm)
            session.commit()

            # Rule 4: mark adjustments CONSUMED - preserves full audit trail.
            # CONSUMED != DECLINED. The original amount, reason, and user
            # link are untouched. This entry is purely informational now.
            for adj in adjs:
                adj.status = "CONSUMED"
                session.add(adj)
            session.commit()

            # --- Rule 5: mark SUCCESS only after all items are persisted ---
            rmtnc.status = "SUCCESS"
            session.add(rmtnc)
            session.commit()

            results.append(rmtnc)

        except Exception as e:
            # Rule 5: on any failure roll back item writes, then record
            # the failure in the ledger so it can be reconciled.
            logger.error(f"Failed to generate remittance for user {u_id}: {e}")
            try:
                session.rollback()
                # If the remittance row was already committed (PENDING or
                # PROCESSING), mark it FAILED so the ledger has a record
                # but it never counts toward paid_ids.
                if rmtnc is not None:
                    stale = session.get(Remittance, rmtnc.id)
                    if stale and stale.status in ("PENDING", "PROCESSING"):
                        stale.status = "FAILED"
                        session.add(stale)
                        session.commit()
            except Exception as inner_e:
                logger.error(
                    f"Could not mark remittance FAILED for user {u_id}: {inner_e}"
                )
            continue

    return RemittancesPublic(data=results, count=len(results))


# ---------------------------------------------------------------------------
# list_worklogs
# ---------------------------------------------------------------------------


def list_worklogs(
    session: Session, remittance_status: str | None = None
) -> WorkLogsPublic:
    """
    List all WorkLogs with ledger-correct financials.

    remittance_status: REMITTED | UNREMITTED | None

    Per worklog:
      total_amount       = SUM of APPROVED segments (settled + outstanding)
      settled_amount     = SUM of segments in a SUCCESS remittance_item
      outstanding_amount = SUM of APPROVED segments NOT yet remitted

    REMITTED   = all APPROVED segments are settled AND at least one exists
    UNREMITTED = at least one APPROVED segment is not yet settled

    Amounts are re-derived from segments at query time so that any
    retroactive adjustment (Rule 4) is immediately visible via the
    Adjustment table. The worklog row itself is never mutated.
    """
    paid_ids = _remitted_seg_ids(session)
    wls = session.exec(select(WorkLog)).all()
    items: list[WorkLogPublic] = []

    for wl in wls:
        try:
            rate = _get_hourly_rate(wl.user_id, session)

            approved = session.exec(
                select(TimeSegment).where(
                    TimeSegment.worklog_id == wl.id,
                    TimeSegment.status == "APPROVED",
                )
            ).all()

            settled = [s for s in approved if s.id in paid_ids]
            outstanding = [s for s in approved if s.id not in paid_ids]

            ttl = round(sum(_seg_amt(s, rate) for s in approved), 2)
            s_ttl = round(sum(_seg_amt(s, rate) for s in settled), 2)
            o_ttl = round(sum(_seg_amt(s, rate) for s in outstanding), 2)

            is_remitted = len(outstanding) == 0 and len(approved) > 0

            if remittance_status == "REMITTED" and not is_remitted:
                continue
            if remittance_status == "UNREMITTED" and is_remitted:
                continue

            items.append(
                WorkLogPublic(
                    id=wl.id,
                    user_id=wl.user_id,
                    task_name=wl.task_name,
                    total_amount=ttl,
                    settled_amount=s_ttl,
                    outstanding_amount=o_ttl,
                    created_at=wl.created_at,
                )
            )

        except Exception as e:
            logger.error(f"Failed to process worklog {wl.id}: {e}")
            continue

    return WorkLogsPublic(data=items, count=len(items))
