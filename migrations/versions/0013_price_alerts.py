"""افزودنِ جدولِ هشدارِ قیمت: price_alerts (برای .هشدارقیمت)

Revision ID: 0013_price_alerts
Revises: 0012_profanity_filter
Create Date: 2026-08-29

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0013_price_alerts"
down_revision: Union[str, None] = "0012_profanity_filter"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "price_alerts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("item_key", sa.String(length=64), nullable=False),
        sa.Column("item_label", sa.Text(), nullable=False),
        sa.Column("direction", sa.String(length=8), nullable=False),  # "above" | "below"
        sa.Column("target_price", sa.Float(), nullable=False),
        sa.Column("triggered", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_price_alerts_chat_id", "price_alerts", ["chat_id"])
    op.create_index("ix_price_alerts_triggered", "price_alerts", ["triggered"])


def downgrade() -> None:
    op.drop_table("price_alerts")
