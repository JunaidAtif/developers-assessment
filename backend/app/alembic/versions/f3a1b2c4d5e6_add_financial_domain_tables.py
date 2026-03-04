"""Add financial domain tables: work_log, time_segment, remittance, remittance_line

Revision ID: f3a1b2c4d5e6
Revises: 1a31ce608336
Create Date: 2026-03-03 00:00:00.000000
"""

import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "f3a1b2c4d5e6"
down_revision = "1a31ce608336"
branch_labels = None
depends_on = None


def upgrade():
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')

    # ------------------------------------------------------------------
    # work_log
    # ------------------------------------------------------------------
    op.create_table(
        "work_log",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuid_generate_v4()"),
            nullable=False,
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("task_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column(
            "status",
            sqlmodel.sql.sqltypes.AutoString(),
            nullable=False,
            server_default="OPEN",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    op.create_index("ix_work_log_user_id", "work_log", ["user_id"])
    op.create_index("ix_work_log_task_id", "work_log", ["task_id"])
    op.create_index("ix_work_log_status", "work_log", ["status"])
    op.create_index("ix_work_log_created_at", "work_log", ["created_at"])

    # ------------------------------------------------------------------
    # time_segment
    # ------------------------------------------------------------------
    op.create_table(
        "time_segment",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuid_generate_v4()"),
            nullable=False,
        ),
        sa.Column("worklog_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("hours", sa.Float(), nullable=False),
        sa.Column("rate", sa.Float(), nullable=False),
        sa.Column(
            "status",
            sqlmodel.sql.sqltypes.AutoString(),
            nullable=False,
            server_default="APPROVED",
        ),
        sa.Column(
            "recorded_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    op.create_index("ix_time_segment_worklog_id", "time_segment", ["worklog_id"])
    op.create_index("ix_time_segment_status", "time_segment", ["status"])
    op.create_index("ix_time_segment_recorded_at", "time_segment", ["recorded_at"])

    # ------------------------------------------------------------------
    # remittance
    # ------------------------------------------------------------------
    op.create_table(
        "remittance",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuid_generate_v4()"),
            nullable=False,
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("period", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("total_amount", sa.Float(), nullable=False),
        sa.Column(
            "status",
            sqlmodel.sql.sqltypes.AutoString(),
            nullable=False,
            server_default="PENDING",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("processed_at", sa.DateTime(), nullable=True),
    )

    op.create_index("ix_remittance_user_id", "remittance", ["user_id"])
    op.create_index("ix_remittance_period", "remittance", ["period"])
    op.create_index("ix_remittance_status", "remittance", ["status"])
    op.create_index("ix_remittance_created_at", "remittance", ["created_at"])

    # ------------------------------------------------------------------
    # remittance_line (CRITICAL)
    # ------------------------------------------------------------------
    op.create_table(
        "remittance_line",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuid_generate_v4()"),
            nullable=False,
        ),
        sa.Column("remittance_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("worklog_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("amount", sa.Float(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    op.create_index(
        "ix_remittance_line_remittance_id",
        "remittance_line",
        ["remittance_id"],
    )
    op.create_index(
        "ix_remittance_line_worklog_id",
        "remittance_line",
        ["worklog_id"],
    )


def downgrade():
    op.drop_table("remittance_line")
    op.drop_table("remittance")
    op.drop_table("time_segment")
    op.drop_table("work_log")