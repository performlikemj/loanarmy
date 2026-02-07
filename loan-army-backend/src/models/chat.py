"""
Chat Models for Academy Watch AI Agent

Stores chat sessions and messages for the interactive analyst feature.
"""

from datetime import datetime, timezone
from sqlalchemy import CheckConstraint
from src.models.league import db


class ChatSession(db.Model):
    """Per-user chat session with the AI agent."""
    __tablename__ = 'chat_sessions'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user_accounts.id'), nullable=False)
    title = db.Column(db.String(200))
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    # Optional context selectors (what data is loaded for this session)
    team_id = db.Column(db.Integer, db.ForeignKey('teams.id'), nullable=True)
    league_id = db.Column(db.Integer, db.ForeignKey('leagues.id'), nullable=True)

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                          onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    user = db.relationship('UserAccount', backref=db.backref('chat_sessions', lazy='dynamic'))
    team = db.relationship('Team', lazy=True)
    league = db.relationship('League', lazy=True)
    messages = db.relationship('ChatMessage', backref='session', lazy='dynamic',
                               order_by='ChatMessage.created_at',
                               cascade='all, delete-orphan')

    def __repr__(self):
        return f'<ChatSession id={self.id} user_id={self.user_id} title={self.title!r}>'

    def to_dict(self, include_messages=False):
        data = {
            'id': self.id,
            'user_id': self.user_id,
            'title': self.title,
            'is_active': self.is_active,
            'team_id': self.team_id,
            'league_id': self.league_id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }
        if include_messages:
            data['messages'] = [m.to_dict() for m in self.messages.all()]
        return data


class ChatMessage(db.Model):
    """Individual messages in a chat session."""
    __tablename__ = 'chat_messages'
    __table_args__ = (
        CheckConstraint("role IN ('user', 'assistant', 'system')", name='valid_role'),
    )

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('chat_sessions.id'), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # 'user', 'assistant', 'system'
    content = db.Column(db.Text, nullable=False)
    metadata_json = db.Column(db.Text)  # JSON: tool calls, charts, tables
    tokens_used = db.Column(db.Integer, default=0)

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f'<ChatMessage id={self.id} session_id={self.session_id} role={self.role!r}>'

    def to_dict(self):
        import json
        metadata = None
        if self.metadata_json:
            try:
                metadata = json.loads(self.metadata_json)
            except (json.JSONDecodeError, TypeError):
                metadata = None

        return {
            'id': self.id,
            'session_id': self.session_id,
            'role': self.role,
            'content': self.content,
            'metadata': metadata,
            'tokens_used': self.tokens_used,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }
