"""Player Social API endpoints for The Academy Watch.

Handles:
- Player comments (CRUD + voting)
- Player video submissions (YouTube links + voting)
"""
from flask import Blueprint, request, jsonify, g
from src.models.league import (
    db, PlayerComment, PlayerCommentVote, PlayerVideo, PlayerVideoVote, UserAccount
)
from src.routes.api import require_user_auth
from src.extensions import limiter
from src.utils.sanitize import sanitize_plain_text
from datetime import datetime, timezone
import logging
import re

player_social_bp = Blueprint('player_social', __name__)
logger = logging.getLogger(__name__)

# Constraints
MAX_COMMENT_LENGTH = 1000
DOWNVOTE_HIDE_THRESHOLD = 5

# Rate limits
RATE_LIMIT_PER_MINUTE = "10 per minute"
RATE_LIMIT_PER_HOUR = "30 per hour"

# YouTube URL patterns
_YOUTUBE_PATTERNS = [
    re.compile(r'(?:https?://)?(?:www\.)?youtube\.com/watch\?.*v=([a-zA-Z0-9_-]{11})'),
    re.compile(r'(?:https?://)?youtu\.be/([a-zA-Z0-9_-]{11})'),
    re.compile(r'(?:https?://)?(?:www\.)?youtube\.com/embed/([a-zA-Z0-9_-]{11})'),
]


def _extract_youtube_id(url: str) -> str | None:
    """Extract YouTube video ID from a URL. Returns None if invalid."""
    if not url:
        return None
    for pattern in _YOUTUBE_PATTERNS:
        match = pattern.search(url)
        if match:
            return match.group(1)
    return None


def _is_valid_youtube_url(url: str) -> bool:
    """Check that the URL is from youtube.com or youtu.be domains only."""
    if not url:
        return False
    url_lower = url.lower()
    return ('youtube.com/' in url_lower or 'youtu.be/' in url_lower)


# =============================================================================
# Player Comments
# =============================================================================

@player_social_bp.route('/players/<int:player_api_id>/comments', methods=['GET'])
def list_comments(player_api_id):
    """List comments for a player (paginated).

    Query params:
    - sort: 'newest' (default) or 'top'
    - limit: Max results (default 20, max 100)
    - offset: Pagination offset
    - include_hidden: Show hidden comments (default false)
    """
    sort = request.args.get('sort', 'newest')
    limit = min(request.args.get('limit', 20, type=int), 100)
    offset = request.args.get('offset', 0, type=int)
    include_hidden = request.args.get('include_hidden', 'false').lower() == 'true'

    query = PlayerComment.query.filter_by(player_api_id=player_api_id)

    if not include_hidden:
        query = query.filter_by(is_hidden=False)

    if sort == 'top':
        query = query.order_by((PlayerComment.upvotes - PlayerComment.downvotes).desc(), PlayerComment.created_at.desc())
    else:
        query = query.order_by(PlayerComment.created_at.desc())

    total = query.count()
    comments = query.offset(offset).limit(limit).all()

    return jsonify({
        'comments': [c.to_dict() for c in comments],
        'total': total,
        'limit': limit,
        'offset': offset,
    })


@player_social_bp.route('/players/<int:player_api_id>/comments', methods=['POST'])
@require_user_auth
@limiter.limit(RATE_LIMIT_PER_MINUTE)
@limiter.limit(RATE_LIMIT_PER_HOUR)
def create_comment(player_api_id):
    """Submit a comment on a player profile. Requires authentication."""
    user = getattr(g, 'user', None)
    if not user:
        return jsonify({'error': 'authentication required'}), 401

    data = request.get_json(silent=True)
    if not data:
        return jsonify({'error': 'request body required'}), 400

    content = (data.get('content') or '').strip()
    if not content:
        return jsonify({'error': 'content is required'}), 400

    content = sanitize_plain_text(content)
    if len(content) > MAX_COMMENT_LENGTH:
        return jsonify({'error': f'content must be {MAX_COMMENT_LENGTH} characters or fewer'}), 400

    comment = PlayerComment(
        player_api_id=player_api_id,
        user_id=user.id,
        content=content,
    )
    db.session.add(comment)
    db.session.commit()

    return jsonify({'comment': comment.to_dict()}), 201


@player_social_bp.route('/players/comments/<int:comment_id>/vote', methods=['POST'])
@limiter.limit(RATE_LIMIT_PER_MINUTE)
def vote_comment(comment_id):
    """Upvote or downvote a comment. Body: {vote: 1} or {vote: -1}."""
    comment = db.session.get(PlayerComment, comment_id)
    if not comment:
        return jsonify({'error': 'comment not found'}), 404

    data = request.get_json(silent=True)
    if not data or data.get('vote') not in (1, -1):
        return jsonify({'error': 'vote must be 1 or -1'}), 400

    vote_value = data['vote']

    # Identify voter
    auth = request.headers.get('Authorization', '')
    user_id = None
    session_id = None

    if auth.startswith('Bearer '):
        user = getattr(g, 'user', None)
        if user:
            user_id = user.id

    if not user_id:
        session_id = request.headers.get('X-Session-Id') or request.cookies.get('session_id')

    # Check for existing vote
    existing = None
    if user_id:
        existing = PlayerCommentVote.query.filter_by(comment_id=comment_id, user_id=user_id).first()
    elif session_id:
        existing = PlayerCommentVote.query.filter_by(comment_id=comment_id, session_id=session_id).first()

    if existing:
        if existing.vote == vote_value:
            return jsonify({'message': 'already voted', 'comment': comment.to_dict()}), 200
        # Change vote
        old_vote = existing.vote
        existing.vote = vote_value
        if old_vote == 1:
            comment.upvotes = max((comment.upvotes or 0) - 1, 0)
        else:
            comment.downvotes = max((comment.downvotes or 0) - 1, 0)
        if vote_value == 1:
            comment.upvotes = (comment.upvotes or 0) + 1
        else:
            comment.downvotes = (comment.downvotes or 0) + 1
    else:
        new_vote = PlayerCommentVote(
            comment_id=comment_id,
            user_id=user_id,
            session_id=session_id,
            vote=vote_value,
        )
        db.session.add(new_vote)
        if vote_value == 1:
            comment.upvotes = (comment.upvotes or 0) + 1
        else:
            comment.downvotes = (comment.downvotes or 0) + 1

    # Auto-hide if downvotes exceed threshold
    if (comment.downvotes or 0) >= DOWNVOTE_HIDE_THRESHOLD:
        comment.is_hidden = True

    db.session.commit()
    return jsonify({'comment': comment.to_dict()})


@player_social_bp.route('/players/comments/<int:comment_id>', methods=['DELETE'])
@require_user_auth
def delete_comment(comment_id):
    """Delete own comment. Auth required, owner only."""
    user = getattr(g, 'user', None)
    if not user:
        return jsonify({'error': 'authentication required'}), 401

    comment = db.session.get(PlayerComment, comment_id)
    if not comment:
        return jsonify({'error': 'comment not found'}), 404

    if comment.user_id != user.id:
        return jsonify({'error': 'not authorized to delete this comment'}), 403

    db.session.delete(comment)
    db.session.commit()

    return jsonify({'message': 'comment deleted'}), 200


# =============================================================================
# Player Videos
# =============================================================================

@player_social_bp.route('/players/<int:player_api_id>/videos', methods=['GET'])
def list_videos(player_api_id):
    """List YouTube videos for a player (sorted by upvotes).

    Query params:
    - limit: Max results (default 20, max 100)
    - offset: Pagination offset
    """
    limit = min(request.args.get('limit', 20, type=int), 100)
    offset = request.args.get('offset', 0, type=int)

    query = PlayerVideo.query.filter_by(player_api_id=player_api_id, status='approved')
    query = query.order_by((PlayerVideo.upvotes - PlayerVideo.downvotes).desc(), PlayerVideo.created_at.desc())

    total = query.count()
    videos = query.offset(offset).limit(limit).all()

    return jsonify({
        'videos': [v.to_dict() for v in videos],
        'total': total,
        'limit': limit,
        'offset': offset,
    })


@player_social_bp.route('/players/<int:player_api_id>/videos', methods=['POST'])
@require_user_auth
@limiter.limit(RATE_LIMIT_PER_MINUTE)
@limiter.limit(RATE_LIMIT_PER_HOUR)
def submit_video(player_api_id):
    """Submit a YouTube video for a player. Requires authentication."""
    user = getattr(g, 'user', None)
    if not user:
        return jsonify({'error': 'authentication required'}), 401

    data = request.get_json(silent=True)
    if not data:
        return jsonify({'error': 'request body required'}), 400

    youtube_url = (data.get('youtube_url') or '').strip()
    if not youtube_url:
        return jsonify({'error': 'youtube_url is required'}), 400

    if not _is_valid_youtube_url(youtube_url):
        return jsonify({'error': 'only YouTube URLs are allowed'}), 400

    youtube_id = _extract_youtube_id(youtube_url)
    if not youtube_id:
        return jsonify({'error': 'could not extract video ID from URL'}), 400

    # Check for duplicate
    existing = PlayerVideo.query.filter_by(player_api_id=player_api_id, youtube_id=youtube_id).first()
    if existing:
        return jsonify({'error': 'this video has already been submitted for this player'}), 409

    title = sanitize_plain_text((data.get('title') or '').strip()) or None
    if title and len(title) > 300:
        title = title[:300]

    video = PlayerVideo(
        player_api_id=player_api_id,
        submitted_by=user.id,
        youtube_url=youtube_url,
        youtube_id=youtube_id,
        title=title,
    )
    db.session.add(video)
    db.session.commit()

    return jsonify({'video': video.to_dict()}), 201


@player_social_bp.route('/players/videos/<int:video_id>/vote', methods=['POST'])
@limiter.limit(RATE_LIMIT_PER_MINUTE)
def vote_video(video_id):
    """Upvote or downvote a video. Body: {vote: 1} or {vote: -1}."""
    video = db.session.get(PlayerVideo, video_id)
    if not video:
        return jsonify({'error': 'video not found'}), 404

    data = request.get_json(silent=True)
    if not data or data.get('vote') not in (1, -1):
        return jsonify({'error': 'vote must be 1 or -1'}), 400

    vote_value = data['vote']

    # Identify voter
    auth = request.headers.get('Authorization', '')
    user_id = None
    session_id = None

    if auth.startswith('Bearer '):
        user = getattr(g, 'user', None)
        if user:
            user_id = user.id

    if not user_id:
        session_id = request.headers.get('X-Session-Id') or request.cookies.get('session_id')

    # Check for existing vote
    existing = None
    if user_id:
        existing = PlayerVideoVote.query.filter_by(video_id=video_id, user_id=user_id).first()
    elif session_id:
        existing = PlayerVideoVote.query.filter_by(video_id=video_id, session_id=session_id).first()

    if existing:
        if existing.vote == vote_value:
            return jsonify({'message': 'already voted', 'video': video.to_dict()}), 200
        old_vote = existing.vote
        existing.vote = vote_value
        if old_vote == 1:
            video.upvotes = max((video.upvotes or 0) - 1, 0)
        else:
            video.downvotes = max((video.downvotes or 0) - 1, 0)
        if vote_value == 1:
            video.upvotes = (video.upvotes or 0) + 1
        else:
            video.downvotes = (video.downvotes or 0) + 1
    else:
        new_vote = PlayerVideoVote(
            video_id=video_id,
            user_id=user_id,
            session_id=session_id,
            vote=vote_value,
        )
        db.session.add(new_vote)
        if vote_value == 1:
            video.upvotes = (video.upvotes or 0) + 1
        else:
            video.downvotes = (video.downvotes or 0) + 1

    db.session.commit()
    return jsonify({'video': video.to_dict()})
