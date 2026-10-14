"""add word filter, warn, activity, poll models

Revision ID: 0010
Revises: 0009_assistant_schedule
Create Date: 2026-08-27 07:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0010'
down_revision: Union[str, None] = '0009_assistant_schedule'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # GroupWordFilter
    op.create_table('group_word_filters',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('chat_id', sa.BigInteger(), nullable=False),
        sa.Column('word', sa.Text(), nullable=False),
        sa.Column('action', sa.String(length=16), server_default='delete', nullable=False),
        sa.Column('case_sensitive', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('is_regex', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('chat_id', 'word', name='uq_group_word_filters_chat_word')
    )
    op.create_index('ix_group_word_filters_chat_id', 'group_word_filters', ['chat_id'])

    # GroupUserWarning
    op.create_table('group_user_warnings',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('chat_id', sa.BigInteger(), nullable=False),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('warn_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('last_warn_time', sa.DateTime(timezone=True), nullable=True),
        sa.Column('muted_until', sa.DateTime(timezone=True), nullable=True),
        sa.Column('kicked', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('banned', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('chat_id', 'user_id', name='uq_group_user_warnings_chat_user')
    )
    op.create_index('ix_group_user_warnings_chat_id', 'group_user_warnings', ['chat_id'])

    # GroupWarnSettings
    op.create_table('group_warn_settings',
        sa.Column('chat_id', sa.BigInteger(), nullable=False),
        sa.Column('enabled', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('warn_limit', sa.Integer(), server_default='3', nullable=False),
        sa.Column('action_on_limit', sa.String(length=16), server_default='mute', nullable=False),
        sa.Column('mute_duration_minutes', sa.Integer(), server_default='60', nullable=False),
        sa.Column('auto_reset_days', sa.Integer(), server_default='7', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('chat_id'),
        sa.UniqueConstraint('chat_id', name='uq_group_warn_settings_chat_id')
    )

    # GroupActivityLog
    op.create_table('group_activity_log',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('chat_id', sa.BigInteger(), nullable=False),
        sa.Column('log_date', sa.String(length=10), nullable=False),
        sa.Column('messages_sent', sa.Integer(), server_default='0', nullable=False),
        sa.Column('warnings_given', sa.Integer(), server_default='0', nullable=False),
        sa.Column('messages_deleted', sa.Integer(), server_default='0', nullable=False),
        sa.Column('members_joined', sa.Integer(), server_default='0', nullable=False),
        sa.Column('members_left', sa.Integer(), server_default='0', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_group_activity_log_chat_id', 'group_activity_log', ['chat_id'])
    op.create_index('ix_group_activity_log_date', 'group_activity_log', ['log_date'])

    # GroupPoll
    op.create_table('group_polls',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('chat_id', sa.BigInteger(), nullable=False),
        sa.Column('message_id', sa.Integer(), nullable=False),
        sa.Column('poll_id', sa.String(length=64), nullable=False),
        sa.Column('question', sa.Text(), nullable=False),
        sa.Column('options', sa.Text(), nullable=False),  # JSON list
        sa.Column('total_votes', sa.Integer(), server_default='0', nullable=False),
        sa.Column('closed', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_group_polls_chat_id', 'group_polls', ['chat_id'])
    op.create_index('ix_group_polls_created_at', 'group_polls', ['created_at'])


def downgrade() -> None:
    op.drop_table('group_polls')
    op.drop_table('group_activity_log')
    op.drop_table('group_warn_settings')
    op.drop_table('group_user_warnings')
    op.drop_table('group_word_filters')