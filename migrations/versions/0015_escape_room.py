"""اتاق فرار متنی (`.فرار`) — جدول‌های بازی

Revision ID: 0015_escape_room
Revises: 0014_media_locks_recurring
Create Date: 2026-08-31

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0015_escape_room"
down_revision: Union[str, None] = "0014_media_locks_recurring"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "escape_sessions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_escape_sessions_user", "escape_sessions", ["user_id"])

    op.create_table(
        "escape_scores",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("scenario", sa.String(length=32), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("solved_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("elapsed_seconds", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("won", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_escape_scores_user_score", "escape_scores", ["user_id", "score"])
    op.create_index("ix_escape_scores_won", "escape_scores", ["won"])

    op.create_table(
        "escape_daily",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("day", sa.String(length=10), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reward_xp", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("chat_id", "user_id", "day", name="uq_escape_daily_day"),
    )


def downgrade() -> None:
    op.drop_table("escape_daily")
    op.drop_index("ix_escape_scores_won", table_name="escape_scores")
    op.drop_index("ix_escape_scores_user_score", table_name="escape_scores")
    op.drop_table("escape_scores")
    op.drop_index("ix_escape_sessions_user", table_name="escape_sessions")
    op.drop_table("escape_sessions")
