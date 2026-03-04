"""Redesign financial schema: drop old 4-table layout, create 5-table layout + hourly_rate on user

Old layout  : work_log, time_segment (old cols), remittance (old cols), remittance_line
New layout  : worklog, time_segment (redesigned), remittance (redesigned),
              remittance_item, adjustment
Also adds   : user.hourly_rate FLOAT NOT NULL DEFAULT 0.0

Revision ID: c2d3e4f5a6b7
Revises: b1c2d3e4f5a6
Create Date: 2026-03-05 00:00:00.000000
"""

import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "c2d3e4f5a6b7"
down_revision = "b1c2d3e4f5a6"
branch_labels = None
depends_on = None


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

UUID = postgresql.UUID(as_uuid=True)
_uuid_default = sa.text("uuid_generate_v4()")
_now = sa.text("now()")


def upgrade():
    # ------------------------------------------------------------------ #
    # 1.  Tear down old FK constraints before dropping tables             #
    # ------------------------------------------------------------------ #

    # FK constraints from b1c2d3e4f5a6 are still on the old tables.
    # Drop them so the tables can be removed cleanly.
    with op.batch_alter_table("remittance_line") as batch_op:
        batch_op.drop_constraint(
            "fk_remittance_line_remittance_id_remittance", type_="foreignkey"
        )
        batch_op.drop_constraint(
            "fk_remittance_line_worklog_id_work_log", type_="foreignkey"
        )

    with op.batch_alter_table("remittance") as batch_op:
        batch_op.drop_constraint("fk_remittance_user_id_user", type_="foreignkey")

    with op.batch_alter_table("time_segment") as batch_op:
        batch_op.drop_constraint(
            "fk_time_segment_worklog_id_work_log", type_="foreignkey"
        )

    with op.batch_alter_table("work_log") as batch_op:
        batch_op.drop_constraint("fk_work_log_user_id_user", type_="foreignkey")

    # ------------------------------------------------------------------ #
    # 2.  Drop old tables (FK-safe order: children first)                 #
    # ------------------------------------------------------------------ #

    op.drop_table("remittance_line")
    op.drop_table("remittance")
    op.drop_table("time_segment")
    op.drop_table("work_log")

    # ------------------------------------------------------------------ #
    # 3.  Add hourly_rate to user table                                   #
    # ------------------------------------------------------------------ #

    op.add_column(
        "user",
        sa.Column(
            "hourly_rate",
            sa.Float(),
            nullable=False,
            server_default="0.0",
        ),
    )

    # ------------------------------------------------------------------ #
    # 4.  Create worklog                                                  #
    # ------------------------------------------------------------------ #

    op.create_table(
        "worklog",
        sa.Column(
            "id",
            UUID,
            primary_key=True,
            server_default=_uuid_default,
            nullable=False,
        ),
        sa.Column("user_id", UUID, sa.ForeignKey("user.id", ondelete="CASCADE"), nullable=False),
        sa.Column("task_name", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=_now),
    )

    op.create_index("ix_worklog_user_id", "worklog", ["user_id"])
    op.create_index("ix_worklog_task_name", "worklog", ["task_name"])
    op.create_index("ix_worklog_created_at", "worklog", ["created_at"])

    # ------------------------------------------------------------------ #
    # 5.  Create time_segment (redesigned)                                #
    # ------------------------------------------------------------------ #

    op.create_table(
        "time_segment",
        sa.Column(
            "id",
            UUID,
            primary_key=True,
            server_default=_uuid_default,
            nullable=False,
        ),
        sa.Column(
            "worklog_id",
            UUID,
            sa.ForeignKey("worklog.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            UUID,
            sa.ForeignKey("user.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("start_time", sa.DateTime(), nullable=False),
        sa.Column("end_time", sa.DateTime(), nullable=False),
        sa.Column("duration_minutes", sa.Float(), nullable=False),
        sa.Column(
            "status",
            sqlmodel.sql.sqltypes.AutoString(),
            nullable=False,
            server_default="PENDING",
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=_now),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=_now),
    )

    op.create_index("ix_time_segment_worklog_id", "time_segment", ["worklog_id"])
    op.create_index("ix_time_segment_user_id", "time_segment", ["user_id"])
    op.create_index("ix_time_segment_status", "time_segment", ["status"])
    op.create_index("ix_time_segment_created_at", "time_segment", ["created_at"])

    # ------------------------------------------------------------------ #
    # 6.  Create remittance (redesigned)                                  #
    # ------------------------------------------------------------------ #

    op.create_table(
        "remittance",
        sa.Column(
            "id",
            UUID,
            primary_key=True,
            server_default=_uuid_default,
            nullable=False,
        ),
        sa.Column(
            "user_id",
            UUID,
            sa.ForeignKey("user.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("period_start", sa.DateTime(), nullable=False),
        sa.Column("period_end", sa.DateTime(), nullable=False),
        sa.Column("total_amount", sa.Float(), nullable=False),
        sa.Column(
            "status",
            sqlmodel.sql.sqltypes.AutoString(),
            nullable=False,
            server_default="PENDING",
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=_now),
    )

    op.create_index("ix_remittance_user_id", "remittance", ["user_id"])
    op.create_index("ix_remittance_period_start", "remittance", ["period_start"])
    op.create_index("ix_remittance_period_end", "remittance", ["period_end"])
    op.create_index("ix_remittance_status", "remittance", ["status"])
    op.create_index("ix_remittance_created_at", "remittance", ["created_at"])

    # ------------------------------------------------------------------ #
    # 7.  Create remittance_item                                          #
    # ------------------------------------------------------------------ #

    op.create_table(
        "remittance_item",
        sa.Column(
            "id",
            UUID,
            primary_key=True,
            server_default=_uuid_default,
            nullable=False,
        ),
        sa.Column(
            "remittance_id",
            UUID,
            sa.ForeignKey("remittance.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "time_segment_id",
            UUID,
            sa.ForeignKey("time_segment.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("amount", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=_now),
    )

    op.create_index(
        "ix_remittance_item_remittance_id", "remittance_item", ["remittance_id"]
    )
    op.create_index(
        "ix_remittance_item_time_segment_id", "remittance_item", ["time_segment_id"]
    )
    op.create_index("ix_remittance_item_created_at", "remittance_item", ["created_at"])

    # ------------------------------------------------------------------ #
    # 8.  Create adjustment                                               #
    # ------------------------------------------------------------------ #

    op.create_table(
        "adjustment",
        sa.Column(
            "id",
            UUID,
            primary_key=True,
            server_default=_uuid_default,
            nullable=False,
        ),
        sa.Column(
            "user_id",
            UUID,
            sa.ForeignKey("user.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "time_segment_id",
            UUID,
            sa.ForeignKey("time_segment.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "worklog_id",
            UUID,
            sa.ForeignKey("worklog.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("amount", sa.Float(), nullable=False),
        sa.Column("reason", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column(
            "status",
            sqlmodel.sql.sqltypes.AutoString(),
            nullable=False,
            server_default="PENDING",
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=_now),
    )

    op.create_index("ix_adjustment_user_id", "adjustment", ["user_id"])
    op.create_index("ix_adjustment_time_segment_id", "adjustment", ["time_segment_id"])
    op.create_index("ix_adjustment_worklog_id", "adjustment", ["worklog_id"])
    op.create_index("ix_adjustment_status", "adjustment", ["status"])
    op.create_index("ix_adjustment_created_at", "adjustment", ["created_at"])


# ---------------------------------------------------------------------------
# Downgrade
# ---------------------------------------------------------------------------


def downgrade():
    # drop new tables in FK-safe order
    op.drop_table("adjustment")
    op.drop_table("remittance_item")
    op.drop_table("remittance")
    op.drop_table("time_segment")
    op.drop_table("worklog")

    # remove hourly_rate from user
    op.drop_column("user", "hourly_rate")

    # restore old tables (mirrors f3a1b2c4d5e6 upgrade)
    op.create_table(
        "work_log",
        sa.Column("id", UUID, primary_key=True, server_default=_uuid_default, nullable=False),
        sa.Column("user_id", UUID, nullable=False),
        sa.Column("task_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column(
            "status",
            sqlmodel.sql.sqltypes.AutoString(),
            nullable=False,
            server_default="OPEN",
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=_now),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=_now),
    )

    op.create_table(
        "time_segment",
        sa.Column("id", UUID, primary_key=True, server_default=_uuid_default, nullable=False),
        sa.Column("worklog_id", UUID, nullable=False),
        sa.Column("hours", sa.Float(), nullable=False),
        sa.Column("rate", sa.Float(), nullable=False),
        sa.Column(
            "status",
            sqlmodel.sql.sqltypes.AutoString(),
            nullable=False,
            server_default="APPROVED",
        ),
        sa.Column("recorded_at", sa.DateTime(), nullable=False, server_default=_now),
    )

    op.create_table(
        "remittance",
        sa.Column("id", UUID, primary_key=True, server_default=_uuid_default, nullable=False),
        sa.Column("user_id", UUID, nullable=False),
        sa.Column("period", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("total_amount", sa.Float(), nullable=False),
        sa.Column(
            "status",
            sqlmodel.sql.sqltypes.AutoString(),
            nullable=False,
            server_default="PENDING",
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=_now),
        sa.Column("processed_at", sa.DateTime(), nullable=True),
    )

    op.create_table(
        "remittance_line",
        sa.Column("id", UUID, primary_key=True, server_default=_uuid_default, nullable=False),
        sa.Column("remittance_id", UUID, nullable=False),
        sa.Column("worklog_id", UUID, nullable=False),
        sa.Column("amount", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=_now),
    )

    # restore FK constraints (mirrors b1c2d3e4f5a6 upgrade)
    op.create_foreign_key(
        "fk_work_log_user_id_user", "work_log", "user", ["user_id"], ["id"], ondelete="CASCADE"
    )
    op.create_foreign_key(
        "fk_time_segment_worklog_id_work_log",
        "time_segment",
        "work_log",
        ["worklog_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_remittance_user_id_user", "remittance", "user", ["user_id"], ["id"], ondelete="CASCADE"
    )
    op.create_foreign_key(
        "fk_remittance_line_remittance_id_remittance",
        "remittance_line",
        "remittance",
        ["remittance_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_remittance_line_worklog_id_work_log",
        "remittance_line",
        "work_log",
        ["worklog_id"],
        ["id"],
        ondelete="CASCADE",
    )
