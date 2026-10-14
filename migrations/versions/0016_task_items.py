"""Task Manager (`.کار`) — جدولِ task_items

Revision ID: 0016_task_items
Revises: 0015_escape_room
Create Date: 2026-09-02

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0016_task_items"
down_revision: Union[str, None] = "0015_escape_room"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "task_items",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("done", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("priority", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_task_items_done", "task_items", ["done"])
    op.create_index("ix_task_items_due_at", "task_items", ["due_at"])


def downgrade() -> None:
    op.drop_index("ix_task_items_due_at", table_name="task_items")
    op.drop_index("ix_task_items_done", table_name="task_items")
    op.drop_table("task_items")
