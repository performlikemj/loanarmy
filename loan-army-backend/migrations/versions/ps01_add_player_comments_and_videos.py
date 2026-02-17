"""add player comments and videos

Revision ID: ps01
Revises: z6b7c8d9e0f1
Create Date: 2026-02-17

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'ps01'
down_revision = 'z6b7c8d9e0f1'
branch_labels = None
depends_on = None


def upgrade():
    # Player comments
    op.create_table(
        'player_comments',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('player_api_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('user_accounts.id'), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('upvotes', sa.Integer(), server_default='0'),
        sa.Column('downvotes', sa.Integer(), server_default='0'),
        sa.Column('is_hidden', sa.Boolean(), server_default='false'),
        sa.Column('reported', sa.Boolean(), server_default='false'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_player_comments_player', 'player_comments', ['player_api_id'])
    op.create_index('ix_player_comments_user', 'player_comments', ['user_id'])

    # Player comment votes
    op.create_table(
        'player_comment_votes',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('comment_id', sa.Integer(), sa.ForeignKey('player_comments.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('user_accounts.id'), nullable=True),
        sa.Column('session_id', sa.String(100), nullable=True),
        sa.Column('vote', sa.SmallInteger(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_comment_votes_comment', 'player_comment_votes', ['comment_id'])
    op.create_unique_constraint('uq_comment_vote_user', 'player_comment_votes', ['comment_id', 'user_id'])

    # Player videos
    op.create_table(
        'player_videos',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('player_api_id', sa.Integer(), nullable=False),
        sa.Column('submitted_by', sa.Integer(), sa.ForeignKey('user_accounts.id'), nullable=False),
        sa.Column('youtube_url', sa.String(500), nullable=False),
        sa.Column('youtube_id', sa.String(20), nullable=False),
        sa.Column('title', sa.String(300), nullable=True),
        sa.Column('upvotes', sa.Integer(), server_default='0'),
        sa.Column('downvotes', sa.Integer(), server_default='0'),
        sa.Column('status', sa.String(20), server_default='approved'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_player_videos_player', 'player_videos', ['player_api_id'])
    op.create_unique_constraint('uq_player_video', 'player_videos', ['player_api_id', 'youtube_id'])

    # Player video votes
    op.create_table(
        'player_video_votes',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('video_id', sa.Integer(), sa.ForeignKey('player_videos.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('user_accounts.id'), nullable=True),
        sa.Column('session_id', sa.String(100), nullable=True),
        sa.Column('vote', sa.SmallInteger(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_video_votes_video', 'player_video_votes', ['video_id'])
    op.create_unique_constraint('uq_video_vote_user', 'player_video_votes', ['video_id', 'user_id'])


def downgrade():
    op.drop_table('player_video_votes')
    op.drop_table('player_videos')
    op.drop_table('player_comment_votes')
    op.drop_table('player_comments')
