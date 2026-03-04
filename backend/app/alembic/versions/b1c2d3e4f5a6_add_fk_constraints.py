"""Add foreign key constraints for financial domain tables

Revision ID: b1c2d3e4f5a6
Revises: f3a1b2c4d5e6
Create Date: 2026-03-04 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "b1c2d3e4f5a6"
down_revision = "f3a1b2c4d5e6"
branch_labels = None
depends_on = None


def upgrade():
    # work_log.user_id -> user.id
    op.create_foreign_key(
        "fk_work_log_user_id_user",
        "work_log",
        "user",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # time_segment.worklog_id -> work_log.id
    op.create_foreign_key(
        "fk_time_segment_worklog_id_work_log",
        "time_segment",
        "work_log",
        ["worklog_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # remittance.user_id -> user.id
    op.create_foreign_key(
        "fk_remittance_user_id_user",
        "remittance",
        "user",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # remittance_line.remittance_id -> remittance.id
    op.create_foreign_key(
        "fk_remittance_line_remittance_id_remittance",
        "remittance_line",
        "remittance",
        ["remittance_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # remittance_line.worklog_id -> work_log.id
    op.create_foreign_key(
        "fk_remittance_line_worklog_id_work_log",
        "remittance_line",
        "work_log",
        ["worklog_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade():
    op.drop_constraint("fk_remittance_line_worklog_id_work_log", "remittance_line", type_="foreignkey")
    op.drop_constraint("fk_remittance_line_remittance_id_remittance", "remittance_line", type_="foreignkey")
    op.drop_constraint("fk_remittance_user_id_user", "remittance", type_="foreignkey")
    op.drop_constraint("fk_time_segment_worklog_id_work_log", "time_segment", type_="foreignkey")
    op.drop_constraint("fk_work_log_user_id_user", "work_log", type_="foreignkey")
