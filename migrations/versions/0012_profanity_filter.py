"""افزودنِ فیلترِ فحش به group_guard_settings (برای .فیلترفحش)

Revision ID: 0012_profanity_filter
Revises: 0011_message_tracker
Create Date: 2026-08-27

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0012_profanity_filter"
down_revision: Union[str, None] = "0011_message_tracker"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "group_guard_settings",
        sa.Column("profanity_filter_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("group_guard_settings", "profanity_filter_enabled")
