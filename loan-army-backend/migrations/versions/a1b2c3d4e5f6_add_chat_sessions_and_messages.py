"""add chat_sessions and chat_messages tables

Revision ID: a1b2c3d4e5f6
Revises: z6b7c8d9e0f1
Create Date: 2026-02-07 16:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = 'z6b7c8d9e0f1'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('chat_sessions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=200), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('team_id', sa.Integer(), nullable=True),
        sa.Column('league_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['league_id'], ['leagues.id'], ),
        sa.ForeignKeyConstraint(['team_id'], ['teams.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['user_accounts.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    op.create_index('ix_chat_sessions_user_active', 'chat_sessions', ['user_id', 'is_active'])

    op.create_table('chat_messages',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('session_id', sa.Integer(), nullable=False),
        sa.Column('role', sa.String(length=20), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('metadata_json', sa.Text(), nullable=True),
        sa.Column('tokens_used', sa.Integer(), nullable=True, server_default=sa.text('0')),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['session_id'], ['chat_sessions.id'], ),
        sa.CheckConstraint("role IN ('user', 'assistant', 'system')", name='valid_role'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_chat_messages_session_id', 'chat_messages', ['session_id'])


def downgrade():
    op.drop_index('ix_chat_messages_session_id', table_name='chat_messages')
    op.drop_table('chat_messages')
    op.drop_index('ix_chat_sessions_user_active', table_name='chat_sessions')
    op.drop_table('chat_sessions')
