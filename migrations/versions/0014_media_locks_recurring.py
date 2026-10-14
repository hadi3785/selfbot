"""قفل‌های رسانه‌ای گروه + یادآوری تکرارشونده

Revision ID: 0014_media_locks_recurring
Revises: 0013_price_alerts
Create Date: 2026-08-30

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0014_media_locks_recurring"
down_revision: Union[str, None] = "0013_price_alerts"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

LOCK_COLUMNS = (
    "lock_sticker",
    "lock_video",
    "lock_audio",
    "lock_voice",
    "lock_gif",
    "lock_photo",
    "lock_game",
    "lock_poll",
)


def upgrade() -> None:
    # ۱) قفل‌های رسانه‌ای روی تنظیماتِ موجودِ هر گروه
    for col in LOCK_COLUMNS:
        op.add_column(
            "group_guard_settings",
            sa.Column(col, sa.Boolean(), nullable=False, server_default=sa.false()),
        )

    # ۲) جدولِ یادآوری/ارسالِ تکرارشونده
    op.create_table(
        "recurring_jobs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False, server_default="reminder"),
        sa.Column("interval_seconds", sa.Integer(), nullable=True),
        sa.Column("daily_hour", sa.SmallInteger(), nullable=True),
        sa.Column("daily_minute", sa.SmallInteger(), nullable=True),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("kind IN ('reminder', 'schedule')", name="ck_recurring_jobs_kind"),
    )
    op.create_index("ix_recurring_jobs_next_run", "recurring_jobs", ["next_run_at"])


def downgrade() -> None:
    op.drop_table("recurring_jobs")
    for col in LOCK_COLUMNS:
        op.drop_column("group_guard_settings", col)
