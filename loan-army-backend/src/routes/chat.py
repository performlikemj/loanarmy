"""
Chat API Routes for Academy Watch Agent

Auth-required endpoints for managing chat sessions and sending messages
to the AI analyst agent.
"""

import asyncio
import concurrent.futures
import json
import logging
import time
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request, g
from src.models.league import db
from src.models.chat import ChatSession, ChatMessage
from src.agents.academy_watch_agent import (
    build_academy_watch_agent,
    set_session_dataframes,
    clear_session_dataframes,
)
from src.services.dataframe_loader import load_context
from src.routes.api import require_user_auth, _user_rate_limit_key
from src.extensions import limiter
from agents import Runner

logger = logging.getLogger(__name__)

chat_bp = Blueprint('chat', __name__)

# --- DataFrame cache (TTL-based, keyed by session_id) ---
_df_cache: dict[int, tuple[float, dict]] = {}
DF_CACHE_TTL = 300  # 5 minutes

MAX_MESSAGES_PER_SESSION = 200


def _get_cached_dataframes(session_id, team_id=None, league_id=None):
    """Load DataFrames with per-session TTL cache."""
    key = session_id
    now = time.time()
    if key in _df_cache:
        ts, dfs = _df_cache[key]
        if now - ts < DF_CACHE_TTL:
            return dfs
    dfs = load_context(team_id=team_id, league_id=league_id)
    _df_cache[key] = (now, dfs)
    return dfs


def _run_agent_sync(agent, messages):
    """Run async agent in a new thread to avoid event loop conflicts."""
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(asyncio.run, Runner.run(agent, messages))
        return future.result(timeout=60)


@chat_bp.route('/chat/sessions', methods=['POST'])
@require_user_auth
@limiter.limit("10 per minute", key_func=_user_rate_limit_key)
def create_session():
    """Create a new chat session for the authenticated user."""
    user = getattr(g, 'user', None)
    if not user:
        return jsonify({'error': 'Authentication required'}), 401

    data = request.get_json(silent=True) or {}
    team_id = data.get('team_id')
    league_id = data.get('league_id')

    # Validate optional IDs are integers
    if team_id is not None:
        try:
            team_id = int(team_id)
        except (ValueError, TypeError):
            return jsonify({'error': 'team_id must be an integer'}), 400
    if league_id is not None:
        try:
            league_id = int(league_id)
        except (ValueError, TypeError):
            return jsonify({'error': 'league_id must be an integer'}), 400

    session = ChatSession(
        user_id=user.id,
        team_id=team_id,
        league_id=league_id,
    )
    db.session.add(session)
    db.session.commit()

    return jsonify(session.to_dict()), 201


@chat_bp.route('/chat/sessions', methods=['GET'])
@require_user_auth
def list_sessions():
    """List chat sessions for the authenticated user."""
    user = getattr(g, 'user', None)
    if not user:
        return jsonify({'error': 'Authentication required'}), 401

    sessions = ChatSession.query.filter_by(
        user_id=user.id, is_active=True
    ).order_by(ChatSession.updated_at.desc()).limit(50).all()

    return jsonify([s.to_dict() for s in sessions])


@chat_bp.route('/chat/sessions/<int:session_id>/history', methods=['GET'])
@require_user_auth
def get_history(session_id):
    """Get message history for a chat session."""
    user = getattr(g, 'user', None)
    if not user:
        return jsonify({'error': 'Authentication required'}), 401

    session = ChatSession.query.filter_by(
        id=session_id, user_id=user.id
    ).first()
    if not session:
        return jsonify({'error': 'Session not found'}), 404

    messages = ChatMessage.query.filter_by(
        session_id=session.id
    ).order_by(ChatMessage.created_at).all()

    return jsonify([m.to_dict() for m in messages])


@chat_bp.route('/chat/sessions/<int:session_id>/messages', methods=['POST'])
@require_user_auth
@limiter.limit("20 per minute", key_func=_user_rate_limit_key)
@limiter.limit("200 per day", key_func=_user_rate_limit_key)
def send_message(session_id):
    """Send a message to the AI analyst and get a response."""
    user = getattr(g, 'user', None)
    if not user:
        return jsonify({'error': 'Authentication required'}), 401

    session = ChatSession.query.filter_by(
        id=session_id, user_id=user.id
    ).first()
    if not session:
        return jsonify({'error': 'Session not found'}), 404

    data = request.get_json(silent=True) or {}
    user_message = (data.get('message') or '').strip()
    if not user_message:
        return jsonify({'error': 'Message is required'}), 400
    if len(user_message) > 4000:
        return jsonify({'error': 'Message too long (max 4000 characters)'}), 400

    # Check max messages per session
    msg_count = ChatMessage.query.filter_by(session_id=session.id).count()
    if msg_count >= MAX_MESSAGES_PER_SESSION:
        return jsonify({'error': f'Session message limit reached ({MAX_MESSAGES_PER_SESSION}). Please start a new session.'}), 400

    # Save user message
    user_msg = ChatMessage(
        session_id=session.id,
        role='user',
        content=user_message,
    )
    db.session.add(user_msg)
    db.session.flush()

    # Load DataFrames for this session's context (cached)
    try:
        dataframes = _get_cached_dataframes(
            session.id,
            team_id=session.team_id,
            league_id=session.league_id,
        )
        set_session_dataframes(session.id, dataframes)
    except Exception as e:
        logger.error("Failed to load data context: %s", e)
        dataframes = {}

    # Build conversation history (last 30 messages to prevent context overflow)
    history = ChatMessage.query.filter_by(
        session_id=session.id
    ).order_by(ChatMessage.created_at.desc()).limit(30).all()
    history.reverse()  # Back to chronological order

    messages = [{'role': m.role, 'content': m.content} for m in history]

    # Run agent
    try:
        agent = build_academy_watch_agent()
        result = _run_agent_sync(agent, messages)

        response_text = result.final_output or ''
        tokens_used = 0
        if hasattr(result, 'raw_responses') and result.raw_responses:
            for resp in result.raw_responses:
                usage = getattr(resp, 'usage', None)
                if usage:
                    tokens_used += getattr(usage, 'total_tokens', 0)

        # Extract metadata (charts, tables) from tool call outputs
        metadata = _extract_metadata(result)

    except Exception as e:
        logger.exception("Agent run failed for session %d", session.id)
        response_text = "I'm sorry, I encountered an error processing your request. Please try again."
        tokens_used = 0
        metadata = {}
    finally:
        clear_session_dataframes(session.id)

    # Auto-generate title from first message
    if not session.title and user_message:
        session.title = user_message[:100]

    # Save assistant response
    assistant_msg = ChatMessage(
        session_id=session.id,
        role='assistant',
        content=response_text,
        metadata_json=json.dumps(metadata) if metadata else None,
        tokens_used=tokens_used,
    )
    db.session.add(assistant_msg)
    session.updated_at = datetime.now(timezone.utc)
    db.session.commit()

    return jsonify({
        'message': response_text,
        'metadata': metadata,
        'tokens_used': tokens_used,
        'message_id': assistant_msg.id,
    })


@chat_bp.route('/chat/sessions/<int:session_id>', methods=['DELETE'])
@require_user_auth
def delete_session(session_id):
    """Soft-delete a chat session (mark as inactive)."""
    user = getattr(g, 'user', None)
    if not user:
        return jsonify({'error': 'Authentication required'}), 401

    session = ChatSession.query.filter_by(
        id=session_id, user_id=user.id
    ).first()
    if not session:
        return jsonify({'error': 'Session not found'}), 404

    session.is_active = False
    db.session.commit()
    return jsonify({'message': 'Session deleted'})


def _extract_metadata(result) -> dict:
    """Extract charts, tables, and tool call info from agent result."""
    metadata = {
        'charts': [],
        'tables': [],
        'tool_calls': [],
    }

    try:
        # Walk through new_items to find tool call outputs
        for item in getattr(result, 'new_items', []):
            # ToolCallOutputItem contains the tool result
            item_type = getattr(item, 'type', '')
            if item_type == 'tool_call_output_item' or hasattr(item, 'output'):
                output_str = getattr(item, 'output', '')
                if isinstance(output_str, str):
                    try:
                        output_data = json.loads(output_str)
                        if isinstance(output_data, dict):
                            charts = output_data.get('charts', [])
                            tables = output_data.get('tables', [])
                            if charts:
                                metadata['charts'].extend(charts)
                            if tables:
                                metadata['tables'].extend(tables)
                    except (json.JSONDecodeError, TypeError):
                        pass

            # Track tool calls for transparency
            if item_type == 'tool_call_item' or hasattr(item, 'name'):
                name = getattr(item, 'name', None)
                if name:
                    metadata['tool_calls'].append({
                        'tool': name,
                    })
    except Exception as e:
        logger.warning("Failed to extract metadata: %s", e)

    # Clean up empty lists
    if not metadata['charts']:
        del metadata['charts']
    if not metadata['tables']:
        del metadata['tables']
    if not metadata['tool_calls']:
        del metadata['tool_calls']

    return metadata
