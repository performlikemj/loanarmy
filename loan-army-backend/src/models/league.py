from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timezone, timedelta
from src.utils.sanitize import sanitize_comment_body, sanitize_plain_text
from sqlalchemy import func


def _as_utc(dt: datetime | None) -> datetime | None:
    """Normalize naive datetimes to UTC-aware values."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)

db = SQLAlchemy()


_db_epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)


def _loan_sort_key(loan) -> tuple[datetime, int]:
    """Sort key prioritising most recently updated loan rows."""
    timestamp = getattr(loan, 'updated_at', None) or getattr(loan, 'created_at', None) or _db_epoch
    loan_id = getattr(loan, 'id', 0) or 0
    return (timestamp, loan_id)


def _dedupe_loans(loans_iterable):
    """Select a single latest entry per player across a sequence of loans."""
    best_by_player = {}
    for loan in loans_iterable:
        if loan is None:
            continue
        player_key = getattr(loan, 'player_id', None)
        if player_key is None:
            player_name = (getattr(loan, 'player_name', '') or '').strip().lower()
            if not player_name:
                continue
            player_key = player_name
        existing = best_by_player.get(player_key)
        if existing is None or _loan_sort_key(loan) > _loan_sort_key(existing):
            best_by_player[player_key] = loan
    deduped = list(best_by_player.values())
    deduped.sort(key=_loan_sort_key, reverse=True)
    return deduped

class League(db.Model):
    __tablename__ = 'leagues'
    
    id = db.Column(db.Integer, primary_key=True)
    league_id = db.Column(db.Integer, unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    country = db.Column(db.String(50), nullable=False)
    logo = db.Column(db.String(255))
    flag = db.Column(db.String(255))
    season = db.Column(db.Integer, nullable=False, default=2024)
    is_european_top_league = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=datetime.now(timezone.utc), onupdate=datetime.now(timezone.utc))
    
    # Relationships
    teams = db.relationship('Team', backref='league', lazy=True)
    
    def to_dict(self):
        return {
            'id': self.id,
            'league_id': self.league_id,
            'name': self.name,
            'country': self.country,
            'logo': self.logo,
            'flag': self.flag,
            'season': self.season,
            'is_european_top_league': self.is_european_top_league,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


class LeagueLocalization(db.Model):
    __tablename__ = 'league_localizations'

    id = db.Column(db.Integer, primary_key=True)
    league_name = db.Column(db.String(100), unique=True, nullable=False)
    country = db.Column(db.String(2), nullable=False)
    search_lang = db.Column(db.String(5), nullable=False)
    ui_lang = db.Column(db.String(10), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=datetime.now(timezone.utc), onupdate=datetime.now(timezone.utc))

    def to_dict(self):
        return {
            'id': self.id,
            'league_name': self.league_name,
            'country': self.country,
            'search_lang': self.search_lang,
            'ui_lang': self.ui_lang,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class Team(db.Model):
    __tablename__ = 'teams'
    
    id = db.Column(db.Integer, primary_key=True)
    team_id = db.Column(db.Integer, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    code = db.Column(db.String(10))
    country = db.Column(db.String(50), nullable=False)
    founded = db.Column(db.Integer)
    national = db.Column(db.Boolean, default=False)
    logo = db.Column(db.String(255))
    venue_name = db.Column(db.String(100))
    venue_address = db.Column(db.String(255))
    venue_city = db.Column(db.String(50))
    venue_capacity = db.Column(db.Integer)
    is_active = db.Column(db.Boolean, default=True)
    newsletters_active = db.Column(db.Boolean, default=False)
    is_tracked = db.Column(db.Boolean, default=False)  # Whether we're actively tracking this team's loans
    league_id = db.Column(db.Integer, db.ForeignKey('leagues.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=datetime.now(timezone.utc), onupdate=datetime.now(timezone.utc))
    season = db.Column(db.Integer, nullable=False)  
    
    __table_args__ = (
        db.UniqueConstraint('team_id', 'season', name='uq_team_id_season'),
    )
      
    # Relationships
    loaned_out_players = db.relationship('LoanedPlayer', 
                                       foreign_keys='LoanedPlayer.primary_team_id',
                                       backref='parent_team', lazy=True)
    loaned_in_players = db.relationship('LoanedPlayer',
                                      foreign_keys='LoanedPlayer.loan_team_id', 
                                      backref='borrowing_team', lazy=True)
    newsletters = db.relationship('Newsletter', backref='team', lazy=True)
    subscriptions = db.relationship('UserSubscription', backref='team', lazy=True)
    
    def unique_active_loans(self):
        """Return active loans with duplicates collapsed to the newest row per player."""
        active = (loan for loan in self.loaned_out_players if getattr(loan, 'is_active', False))
        return _dedupe_loans(active)

    def to_dict(self):
        current_loans = self.unique_active_loans()
        return {
            'id': self.id,
            'team_id': self.team_id,
            'name': self.name,
            'code': self.code,
            'country': self.country,
            'founded': self.founded,
            'national': self.national,
            'logo': self.logo,
            'venue_name': self.venue_name,
            'venue_address': self.venue_address,
            'venue_city': self.venue_city,
            'venue_capacity': self.venue_capacity,
            'is_active': self.is_active,
            'newsletters_active': self.newsletters_active,
            'is_tracked': self.is_tracked,
            'season': self.season,
            'league_name': self.league.name if self.league else None,
            'current_loaned_out_count': len(current_loans),
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

class LoanedPlayer(db.Model):
    __tablename__ = 'loaned_players'
    
    id = db.Column(db.Integer, primary_key=True)
    # Store raw API‑Football player ID directly (no Player FK table anymore)
    player_id = db.Column(db.Integer, nullable=False)
    player_name = db.Column(db.String(100), nullable=False)
    age = db.Column(db.Integer)
    nationality = db.Column(db.String(50))
    primary_team_id = db.Column(db.Integer, db.ForeignKey('teams.id'), nullable=True)  # Nullable for custom teams
    primary_team_name = db.Column(db.String(100), nullable=False)
    loan_team_id = db.Column(db.Integer, db.ForeignKey('teams.id'), nullable=True)  # Nullable for custom teams
    loan_team_name = db.Column(db.String(100), nullable=False)
    team_ids = db.Column(db.String(255))  # Comma-separated list of team IDs
    window_key = db.Column(db.String(50))  # e.g., "2022-23::FULL"
    actual_loan_status = db.Column(db.String(50))  # Active, Terminated, etc.
    legacy_parent_team_id = db.Column(db.Integer)
    legacy_loan_team_id = db.Column(db.Integer)
    reviewer_notes = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True)  # Keep for API compatibility
    appearances = db.Column(db.Integer, default=0)
    goals = db.Column(db.Integer, default=0)
    assists = db.Column(db.Integer, default=0)
    minutes_played = db.Column(db.Integer, default=0)
    yellows = db.Column(db.Integer, default=0)
    reds = db.Column(db.Integer, default=0)
    data_source = db.Column(db.String(50), nullable=False, default='api-football')
    can_fetch_stats = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, default=datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=datetime.now(timezone.utc), onupdate=datetime.now(timezone.utc))
    
    __table_args__ = (
        # Ensure one row per player/parent/loan/window
        db.UniqueConstraint('player_id', 'primary_team_id', 'loan_team_id', 'window_key', name='uq_loans_player_parent_loan_window'),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'player_id': self.player_id,
            'player_name': self.player_name,
            'age': self.age,
            'nationality': self.nationality,
            'primary_team_id': self.primary_team_id,
            'primary_team_name': self.primary_team_name,
            'primary_team_api_id': (self.parent_team.team_id if hasattr(self, 'parent_team') and self.parent_team else None),
            'loan_team_id': self.loan_team_id,
            'loan_team_name': self.loan_team_name,
            'loan_team_api_id': (self.borrowing_team.team_id if hasattr(self, 'borrowing_team') and self.borrowing_team else None),
            'team_ids': self.team_ids,
            'window_key': self.window_key,
            'legacy_parent_team_id': self.legacy_parent_team_id,
            'legacy_loan_team_id': self.legacy_loan_team_id,
            'reviewer_notes': self.reviewer_notes,
            'is_active': self.is_active,
            'appearances': self.appearances,
            'goals': self.goals,
            'assists': self.assists,
            'minutes_played': self.minutes_played,
            'yellows': self.yellows,
            'reds': self.reds,
            'data_source': self.data_source,
            'can_fetch_stats': self.can_fetch_stats,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


class SupplementalLoan(db.Model):
    """DEPRECATED: Use LoanedPlayer with can_fetch_stats=False instead.
    
    This table has been deprecated in favor of unified manual player handling.
    Manual/untrackable players are now identified by:
    - player_id < 0 (negative IDs)
    - can_fetch_stats = False in LoanedPlayer
    - data_source = 'manual' in LoanedPlayer
    
    Historical records remain for reference only. All new manual players should
    be created via LoanedPlayer table using the Players & Loans Manager.
    """
    __tablename__ = 'supplemental_loans'

    id = db.Column(db.Integer, primary_key=True)
    player_name = db.Column(db.String(120), nullable=False)
    parent_team_id = db.Column(db.Integer, db.ForeignKey('teams.id'), nullable=True)
    parent_team_name = db.Column(db.String(120), nullable=False)
    loan_team_id = db.Column(db.Integer, db.ForeignKey('teams.id'), nullable=True)
    loan_team_name = db.Column(db.String(120), nullable=False)
    season_year = db.Column(db.Integer, nullable=False)
    api_player_id = db.Column(db.Integer, nullable=True)
    sofascore_player_id = db.Column(db.Integer, nullable=True)
    data_source = db.Column(db.String(50), nullable=False, default='wikipedia')
    can_fetch_stats = db.Column(db.Boolean, nullable=False, default=False)
    source_url = db.Column(db.String(255))
    wiki_title = db.Column(db.String(255))
    is_verified = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=datetime.now(timezone.utc), onupdate=datetime.now(timezone.utc))

    parent_team = db.relationship('Team', foreign_keys=[parent_team_id], lazy=True)
    loan_team = db.relationship('Team', foreign_keys=[loan_team_id], lazy=True)

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'player_name': self.player_name,
            'parent_team_name': self.parent_team_name,
            'loan_team_name': self.loan_team_name,
            'season_year': self.season_year,
            'data_source': self.data_source,
            'can_fetch_stats': self.can_fetch_stats,
            'source_url': self.source_url,
            'wiki_title': self.wiki_title,
            'is_verified': self.is_verified,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class TeamProfile(db.Model):
    __tablename__ = 'team_profiles'

    team_id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(160), nullable=False)
    code = db.Column(db.String(20))
    country = db.Column(db.String(80))
    founded = db.Column(db.Integer)
    is_national = db.Column(db.Boolean)
    logo_url = db.Column(db.String(255))
    venue_id = db.Column(db.Integer)
    venue_name = db.Column(db.String(160))
    venue_address = db.Column(db.String(255))
    venue_city = db.Column(db.String(120))
    venue_capacity = db.Column(db.Integer)
    venue_surface = db.Column(db.String(80))
    venue_image = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=datetime.now(timezone.utc), onupdate=datetime.now(timezone.utc))

    def to_dict(self):
        return {
            'team_id': self.team_id,
            'name': self.name,
            'code': self.code,
            'country': self.country,
            'founded': self.founded,
            'is_national': self.is_national,
            'logo_url': self.logo_url,
            'venue_id': self.venue_id,
            'venue_name': self.venue_name,
            'venue_address': self.venue_address,
            'venue_city': self.venue_city,
            'venue_capacity': self.venue_capacity,
            'venue_surface': self.venue_surface,
            'venue_image': self.venue_image,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class Player(db.Model):
    __tablename__ = 'players'

    player_id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(160), nullable=False)
    firstname = db.Column(db.String(160))
    lastname = db.Column(db.String(160))
    nationality = db.Column(db.String(80))
    age = db.Column(db.Integer)
    height = db.Column(db.String(32))
    weight = db.Column(db.String(32))
    position = db.Column(db.String(80))
    photo_url = db.Column(db.String(255))
    sofascore_id = db.Column(db.Integer, unique=True)
    created_at = db.Column(db.DateTime, default=datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=datetime.now(timezone.utc), onupdate=datetime.now(timezone.utc))

    def to_dict(self):
        return {
            'player_id': self.player_id,
            'name': self.name,
            'firstname': self.firstname,
            'lastname': self.lastname,
            'nationality': self.nationality,
            'age': self.age,
            'height': self.height,
            'weight': self.weight,
            'position': self.position,
            'photo_url': self.photo_url,
            'sofascore_id': self.sofascore_id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }

class Newsletter(db.Model):
    __tablename__ = 'newsletters'
    
    id = db.Column(db.Integer, primary_key=True)
    team_id = db.Column(db.Integer, db.ForeignKey('teams.id'), nullable=False)
    newsletter_type = db.Column(db.String(20), nullable=False, default='weekly')
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    structured_content = db.Column(db.Text)  # JSON string
    public_slug = db.Column(db.String(200), unique=True, index=True, nullable=False)
    week_start_date = db.Column(db.Date)
    week_end_date = db.Column(db.Date)
    issue_date = db.Column(db.Date)  # The target date for this newsletter issue
    published = db.Column(db.Boolean, default=False)
    published_date = db.Column(db.DateTime)
    email_sent = db.Column(db.Boolean, default=False)
    email_sent_date = db.Column(db.DateTime)
    subscriber_count = db.Column(db.Integer, default=0)
    generated_date = db.Column(db.DateTime, default=datetime.now(timezone.utc))
    created_at = db.Column(db.DateTime, default=datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=datetime.now(timezone.utc), onupdate=datetime.now(timezone.utc))
    
    def to_dict(self):
        return {
            'id': self.id,
            'team_id': self.team_id,
            'team_name': self.team.name if self.team else None,
            'newsletter_type': self.newsletter_type,
            'title': self.title,
            'content': self.content,
            'structured_content': self.structured_content,
            'public_slug': self.public_slug,
            'week_start_date': self.week_start_date.isoformat() if self.week_start_date else None,
            'week_end_date': self.week_end_date.isoformat() if self.week_end_date else None,
            'issue_date': self.issue_date.isoformat() if self.issue_date else None,
            'published': self.published,
            'published_date': self.published_date.isoformat() if self.published_date else None,
            'email_sent': self.email_sent,
            'email_sent_date': self.email_sent_date.isoformat() if self.email_sent_date else None,
            'subscriber_count': self.subscriber_count,
            'generated_date': self.generated_date.isoformat() if self.generated_date else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'commentaries': [c.to_dict() for c in self.commentaries] if self.commentaries else []
        }

class UserSubscription(db.Model):
    __tablename__ = 'user_subscriptions'
    
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), nullable=False)
    team_id = db.Column(db.Integer, db.ForeignKey('teams.id'), nullable=False)
    preferred_frequency = db.Column(db.String(20), default='weekly')
    active = db.Column(db.Boolean, default=True)
    unsubscribe_token = db.Column(db.String(100), unique=True)
    last_email_sent = db.Column(db.DateTime)
    bounce_count = db.Column(db.Integer, default=0)
    email_bounced = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=datetime.now(timezone.utc), onupdate=datetime.now(timezone.utc))
    
    def to_dict(self):
        return {
            'id': self.id,
            'email': self.email,
            'team_id': self.team_id,
            'team': self.team.to_dict() if self.team else None,
            'preferred_frequency': self.preferred_frequency,
            'active': self.active,
            'unsubscribe_token': self.unsubscribe_token,
            'last_email_sent': self.last_email_sent.isoformat() if self.last_email_sent else None,
            'bounce_count': self.bounce_count,
            'email_bounced': self.email_bounced,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

class EmailToken(db.Model):
    __tablename__ = 'email_tokens'

    id = db.Column(db.Integer, primary_key=True)
    token = db.Column(db.String(100), unique=True, nullable=False)
    email = db.Column(db.String(255), nullable=False)
    purpose = db.Column(db.String(50), nullable=False)  # 'verify', 'manage', 'unsubscribe'
    expires_at = db.Column(db.DateTime, nullable=False)
    used_at = db.Column(db.DateTime)
    metadata_json = db.Column(db.Text)  # optional JSON payload
    created_at = db.Column(db.DateTime, default=datetime.now(timezone.utc))

    def is_valid(self) -> bool:
        now = datetime.now(timezone.utc)
        expires = _as_utc(self.expires_at)
        used = _as_utc(self.used_at)
        return (used is None) and (expires is None or expires > now)

    def to_dict(self):
        return {
            'id': self.id,
            'token': self.token,
            'email': self.email,
            'purpose': self.purpose,
            'expires_at': (_as_utc(self.expires_at).isoformat() if self.expires_at else None),
            'used_at': (_as_utc(self.used_at).isoformat() if self.used_at else None),
            'metadata_json': self.metadata_json,
            'created_at': (_as_utc(self.created_at).isoformat() if self.created_at else None),
        }

# New: guest-submitted loan flags
class LoanFlag(db.Model):
    __tablename__ = 'loan_flags'

    id = db.Column(db.Integer, primary_key=True)
    player_api_id = db.Column(db.Integer, nullable=False)
    primary_team_api_id = db.Column(db.Integer, nullable=False)
    loan_team_api_id = db.Column(db.Integer, nullable=True)
    season = db.Column(db.Integer, nullable=True)
    reason = db.Column(db.Text, nullable=False)
    email = db.Column(db.String(255))
    ip_address = db.Column(db.String(64))
    user_agent = db.Column(db.String(512))
    status = db.Column(db.String(20), default='pending')  # pending|resolved
    admin_note = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.now(timezone.utc))
    resolved_at = db.Column(db.DateTime)


class TeamTrackingRequest(db.Model):
    """User requests to track a team's loan players.
    
    When users see a team isn't being tracked, they can submit a request
    which admin can approve or reject.
    """
    __tablename__ = 'team_tracking_requests'

    id = db.Column(db.Integer, primary_key=True)
    team_id = db.Column(db.Integer, db.ForeignKey('teams.id'), nullable=False)
    team_api_id = db.Column(db.Integer, nullable=False)
    team_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(255))
    reason = db.Column(db.Text)
    ip_address = db.Column(db.String(64))
    user_agent = db.Column(db.String(512))
    status = db.Column(db.String(20), default='pending')  # pending|approved|rejected
    admin_note = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.now(timezone.utc))
    resolved_at = db.Column(db.DateTime)

    team = db.relationship('Team', backref='tracking_requests', lazy=True)

    def to_dict(self):
        return {
            'id': self.id,
            'team_id': self.team_id,
            'team_api_id': self.team_api_id,
            'team_name': self.team_name,
            'team_logo': self.team.logo if self.team else None,
            'team_league': self.team.league.name if self.team and self.team.league else None,
            'email': self.email,
            'reason': self.reason,
            'status': self.status,
            'admin_note': self.admin_note,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'resolved_at': self.resolved_at.isoformat() if self.resolved_at else None,
        }


class AdminSetting(db.Model):
    __tablename__ = 'admin_settings'

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), unique=True, nullable=False)
    value_json = db.Column(db.Text, nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.now(timezone.utc), onupdate=datetime.now(timezone.utc))

    def to_dict(self):
        return {
            'key': self.key,
            'value': self.value_json,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class UserAccount(db.Model):
    __tablename__ = 'user_accounts'

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    display_name = db.Column(db.String(80), nullable=False)
    display_name_lower = db.Column(db.String(80), unique=True, nullable=False)
    display_name_confirmed = db.Column(db.Boolean, default=False)
    can_author_commentary = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=datetime.now(timezone.utc), onupdate=datetime.now(timezone.utc))
    last_login_at = db.Column(db.DateTime)
    last_display_name_change_at = db.Column(db.DateTime)

    # Journalist fields
    is_journalist = db.Column(db.Boolean, default=False, nullable=False)
    bio = db.Column(db.Text)
    profile_image_url = db.Column(db.Text)

    # Email preferences
    email_delivery_preference = db.Column(db.String(20), default='individual', nullable=False)  # 'individual' | 'digest'

    comments = db.relationship('NewsletterComment', back_populates='user', lazy=True)
    commentaries = db.relationship('NewsletterCommentary', back_populates='author', lazy=True)
    
    # Relationships for subscriptions
    journalist_subscriptions = db.relationship('JournalistSubscription', 
                                             foreign_keys='JournalistSubscription.journalist_user_id',
                                             backref='journalist', lazy=True)
    subscribed_to = db.relationship('JournalistSubscription',
                                  foreign_keys='JournalistSubscription.subscriber_user_id',
                                  backref='subscriber', lazy=True)

    def to_dict(self):
        return {
            'id': self.id,
            'email': sanitize_plain_text(self.email) if self.email else None,
            'display_name': sanitize_plain_text(self.display_name) if self.display_name else None,
            'display_name_confirmed': bool(self.display_name_confirmed),
            'can_author_commentary': bool(self.can_author_commentary),
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'last_login_at': self.last_login_at.isoformat() if self.last_login_at else None,
            'last_display_name_change_at': self.last_display_name_change_at.isoformat() if self.last_display_name_change_at else None,
            'is_journalist': self.is_journalist,
            'bio': sanitize_plain_text(self.bio) if self.bio else None,
            'profile_image_url': self.profile_image_url,
            'email_delivery_preference': self.email_delivery_preference or 'individual',
        }


class NewsletterComment(db.Model):
    __tablename__ = 'newsletter_comments'

    id = db.Column(db.Integer, primary_key=True)
    newsletter_id = db.Column(db.Integer, db.ForeignKey('newsletters.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user_accounts.id'), nullable=True)
    author_email = db.Column(db.String(255), nullable=False)
    author_name = db.Column(db.String(120))
    author_name_legacy = db.Column(db.String(120))
    body = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=datetime.now(timezone.utc), onupdate=datetime.now(timezone.utc))
    is_deleted = db.Column(db.Boolean, default=False)

    user = db.relationship('UserAccount', back_populates='comments')

    def to_dict(self):
        display_name = None
        display_name_confirmed = None
        if self.user and self.user.display_name:
            current_name = sanitize_plain_text(self.user.display_name)
            display_name_confirmed = bool(self.user.display_name_confirmed)
            legacy_raw = self.author_name_legacy or self.author_name
            legacy = sanitize_plain_text(legacy_raw) if legacy_raw else None
            if legacy and legacy != current_name:
                display_name = f"{legacy} (now: {current_name})"
            else:
                display_name = current_name
        elif self.author_name:
            display_name = sanitize_plain_text(self.author_name)
        return {
            'id': self.id,
            'newsletter_id': self.newsletter_id,
            'author_email': sanitize_plain_text(self.author_email) if self.author_email else None,
            'author_name': sanitize_plain_text(self.author_name) if self.author_name else None,
            'author_name_legacy': sanitize_plain_text(self.author_name_legacy) if self.author_name_legacy else None,
            'author_display_name': display_name,
            'author_display_name_confirmed': display_name_confirmed,
            'user_id': self.user_id,
            'body': sanitize_comment_body(self.body) if not self.is_deleted else '',
            'is_deleted': self.is_deleted,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class NewsletterPlayerYoutubeLink(db.Model):
    """YouTube highlights links for players in newsletters.
    
    Uses player_id for both tracked (positive IDs) and manual (negative IDs) players.
    Manual players are identified by:
    - player_id < 0 (negative IDs from migration or Players & Loans Manager)
    - Corresponding LoanedPlayer.can_fetch_stats = False
    """
    __tablename__ = 'newsletter_player_youtube_links'

    id = db.Column(db.Integer, primary_key=True)
    newsletter_id = db.Column(db.Integer, db.ForeignKey('newsletters.id', ondelete='CASCADE'), nullable=False)
    player_id = db.Column(db.Integer, nullable=False)  # Player ID: positive for tracked, negative for manual players
    player_name = db.Column(db.String(120), nullable=False)  # For display/reference
    youtube_link = db.Column(db.String(500), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=datetime.now(timezone.utc), onupdate=datetime.now(timezone.utc))

    newsletter = db.relationship('Newsletter', backref='youtube_links', lazy=True)

    def to_dict(self):
        return {
            'id': self.id,
            'newsletter_id': self.newsletter_id,
            'player_id': self.player_id,
            'player_name': self.player_name,
            'youtube_link': self.youtube_link,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class NewsletterCommentary(db.Model):
    """Commentary added by authorized authors to newsletters.
    
    Supports three types of commentary:
    - 'player': Commentary attached to a specific player's performance
    - 'intro': Opening commentary for the newsletter
    - 'summary': Closing commentary/wrap-up for the newsletter
    
    All content is sanitized on save to prevent XSS attacks.
    """
    __tablename__ = 'newsletter_commentary'
    
    id = db.Column(db.Integer, primary_key=True)
    newsletter_id = db.Column(db.Integer, db.ForeignKey('newsletters.id', ondelete='CASCADE'), nullable=True)  # Now nullable
    team_id = db.Column(db.Integer, db.ForeignKey('teams.id'), nullable=True)  # For week-based creation
    player_id = db.Column(db.Integer, nullable=True)  # Nullable for intro/summary commentary
    commentary_type = db.Column(db.String(20), nullable=False)  # 'player', 'intro', 'summary'
    content = db.Column(db.Text, nullable=False)  # Sanitized HTML content
    author_id = db.Column(db.Integer, db.ForeignKey('user_accounts.id', ondelete='CASCADE'), nullable=False)
    author_name = db.Column(db.String(120), nullable=False)  # Cached display name
    position = db.Column(db.Integer, default=0, nullable=False)  # For ordering multiple commentaries
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    
    # New fields for journalist articles
    title = db.Column(db.String(200))
    is_premium = db.Column(db.Boolean, default=True, nullable=False)
    
    # Structured blocks for modular content builder (stores array of block objects)
    # Each block has: id, type (text|chart|divider), content, is_premium, position, chart_config
    structured_blocks = db.Column(db.JSON, nullable=True)
    
    # Week-based association fields (for pre-newsletter creation)
    week_start_date = db.Column(db.Date, nullable=True)
    week_end_date = db.Column(db.Date, nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=datetime.now(timezone.utc), onupdate=datetime.now(timezone.utc))
    
    # Relationships
    newsletter = db.relationship('Newsletter', backref='commentaries', lazy=True)
    author = db.relationship('UserAccount', back_populates='commentaries', lazy=True)
    team = db.relationship('Team', lazy=True)
    applause = db.relationship('CommentaryApplause', backref='commentary', lazy='dynamic', cascade='all, delete-orphan')
    
    def to_dict(self):
        from src.utils.sanitize import sanitize_commentary_html, sanitize_plain_text
        
        # Re-sanitize on read as additional safety layer
        safe_content = sanitize_commentary_html(self.content) if self.content else ''
        
        # Get author profile image if author relationship exists
        author_profile_image = None
        if self.author:
            author_profile_image = self.author.profile_image_url
        
        return {
            'id': self.id,
            'newsletter_id': self.newsletter_id,
            'team_id': self.team_id,
            'team_name': self.team.name if self.team else (self.newsletter.team.name if self.newsletter and self.newsletter.team else None),
            'player_id': self.player_id,
            'commentary_type': self.commentary_type,
            'content': safe_content,
            'structured_blocks': self.structured_blocks,
            'author_id': self.author_id,
            'author_name': sanitize_plain_text(self.author_name) if self.author_name else None,
            'author_profile_image': author_profile_image,
            'position': self.position,
            'is_active': self.is_active,
            'title': sanitize_plain_text(self.title) if self.title else None,
            'is_premium': self.is_premium,
            'week_start_date': self.week_start_date.isoformat() if self.week_start_date else None,
            'week_end_date': self.week_end_date.isoformat() if self.week_end_date else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'applause_count': self.applause.count(),
        }
    
    def validate_commentary_type(self):
        """Validate that commentary_type is one of the allowed values."""
        allowed_types = ['player', 'intro', 'summary']
        if self.commentary_type not in allowed_types:
            raise ValueError(f'commentary_type must be one of {allowed_types}, got: {self.commentary_type}')
    
    def validate_player_commentary(self):
        """Validate that player_id is present if commentary_type is 'player'."""
        if self.commentary_type == 'player' and not self.player_id:
            raise ValueError("Player ID is required for player commentary")


class CommentaryApplause(db.Model):
    """Tracks applause/likes for newsletter commentaries."""
    __tablename__ = 'commentary_applause'

    id = db.Column(db.Integer, primary_key=True)
    commentary_id = db.Column(db.Integer, db.ForeignKey('newsletter_commentary.id', ondelete='CASCADE'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user_accounts.id'), nullable=True)
    session_id = db.Column(db.String(100), nullable=True)  # For anonymous tracking
    created_at = db.Column(db.DateTime, default=datetime.now(timezone.utc))

    def to_dict(self):
        return {
            'id': self.id,
            'commentary_id': self.commentary_id,
            'user_id': self.user_id,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }
    
    @staticmethod
    def sanitize_and_create(newsletter_id, author_id, author_name, commentary_type, content, player_id=None, position=0):
        """Factory method that sanitizes content before creating a commentary."""
        from src.utils.sanitize import sanitize_commentary_html
        
        # Sanitize content
        sanitized_content = sanitize_commentary_html(content)
        
        # Create instance
        commentary = NewsletterCommentary(
            newsletter_id=newsletter_id,
            author_id=author_id,
            author_name=author_name,
            commentary_type=commentary_type,
            content=sanitized_content,
            player_id=player_id,
            position=position,
        )
        
        # Validate
        commentary.validate_commentary_type()
        commentary.validate_player_commentary()
        
        return commentary


class JournalistSubscription(db.Model):
    __tablename__ = 'journalist_subscriptions'

    id = db.Column(db.Integer, primary_key=True)
    subscriber_user_id = db.Column(db.Integer, db.ForeignKey('user_accounts.id'), nullable=False)
    journalist_user_id = db.Column(db.Integer, db.ForeignKey('user_accounts.id'), nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=datetime.now(timezone.utc), onupdate=datetime.now(timezone.utc))

    __table_args__ = (
        db.UniqueConstraint('subscriber_user_id', 'journalist_user_id', name='uq_journalist_subscription'),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'subscriber_user_id': self.subscriber_user_id,
            'journalist_user_id': self.journalist_user_id,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class JournalistTeamAssignment(db.Model):
    __tablename__ = 'journalist_team_assignments'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user_accounts.id'), nullable=False)
    team_id = db.Column(db.Integer, db.ForeignKey('teams.id'), nullable=False)
    assigned_at = db.Column(db.DateTime, default=datetime.now(timezone.utc))
    assigned_by = db.Column(db.Integer, db.ForeignKey('user_accounts.id'), nullable=True)

    # Relationships
    journalist = db.relationship('UserAccount', foreign_keys=[user_id], backref=db.backref('assigned_teams', lazy=True))
    team = db.relationship('Team', backref=db.backref('assigned_journalists', lazy=True))
    assigner = db.relationship('UserAccount', foreign_keys=[assigned_by])

    __table_args__ = (
        db.UniqueConstraint('user_id', 'team_id', name='uq_journalist_team_assignment'),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'team_id': self.team_id,
            'team_name': self.team.name if self.team else None,
            'assigned_at': self.assigned_at.isoformat() if self.assigned_at else None,
            'assigned_by': self.assigned_by
        }


class StripeConnectedAccount(db.Model):
    """Stores journalist Stripe Connect account info"""
    __tablename__ = 'stripe_connected_accounts'

    id = db.Column(db.Integer, primary_key=True)
    journalist_user_id = db.Column(db.Integer, db.ForeignKey('user_accounts.id'), nullable=False, unique=True)
    stripe_account_id = db.Column(db.String(255), unique=True, nullable=False)
    onboarding_complete = db.Column(db.Boolean, default=False, nullable=False)
    payouts_enabled = db.Column(db.Boolean, default=False, nullable=False)
    charges_enabled = db.Column(db.Boolean, default=False, nullable=False)
    details_submitted = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=datetime.now(timezone.utc), onupdate=datetime.now(timezone.utc))

    # Relationship
    journalist = db.relationship('UserAccount', foreign_keys=[journalist_user_id], backref=db.backref('stripe_account', uselist=False))

    def to_dict(self):
        return {
            'id': self.id,
            'journalist_user_id': self.journalist_user_id,
            'stripe_account_id': self.stripe_account_id,
            'onboarding_complete': self.onboarding_complete,
            'payouts_enabled': self.payouts_enabled,
            'charges_enabled': self.charges_enabled,
            'details_submitted': self.details_submitted,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


class StripeSubscriptionPlan(db.Model):
    """Journalist-defined subscription pricing"""
    __tablename__ = 'stripe_subscription_plans'

    id = db.Column(db.Integer, primary_key=True)
    journalist_user_id = db.Column(db.Integer, db.ForeignKey('user_accounts.id'), nullable=False)
    stripe_product_id = db.Column(db.String(255), nullable=False)
    stripe_price_id = db.Column(db.String(255), nullable=False, unique=True)
    price_amount = db.Column(db.Integer, nullable=False)  # in cents
    currency = db.Column(db.String(3), default='usd', nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=datetime.now(timezone.utc), onupdate=datetime.now(timezone.utc))

    # Relationship
    journalist = db.relationship('UserAccount', foreign_keys=[journalist_user_id], backref=db.backref('subscription_plans', lazy=True))

    def to_dict(self):
        return {
            'id': self.id,
            'journalist_user_id': self.journalist_user_id,
            'stripe_product_id': self.stripe_product_id,
            'stripe_price_id': self.stripe_price_id,
            'price_amount': self.price_amount,
            'price_display': f"${self.price_amount / 100:.2f}",
            'currency': self.currency,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


class StripeSubscription(db.Model):
    """Tracks active Stripe subscriptions"""
    __tablename__ = 'stripe_subscriptions'

    id = db.Column(db.Integer, primary_key=True)
    subscriber_user_id = db.Column(db.Integer, db.ForeignKey('user_accounts.id'), nullable=False)
    journalist_user_id = db.Column(db.Integer, db.ForeignKey('user_accounts.id'), nullable=False)
    stripe_subscription_id = db.Column(db.String(255), unique=True, nullable=False)
    stripe_customer_id = db.Column(db.String(255), nullable=False)
    status = db.Column(db.String(50), nullable=False)  # active, canceled, past_due, etc.
    current_period_start = db.Column(db.DateTime)
    current_period_end = db.Column(db.DateTime)
    cancel_at_period_end = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=datetime.now(timezone.utc), onupdate=datetime.now(timezone.utc))

    __table_args__ = (
        db.UniqueConstraint('subscriber_user_id', 'journalist_user_id', name='uq_stripe_subscription'),
    )

    # Relationships
    subscriber = db.relationship('UserAccount', foreign_keys=[subscriber_user_id], backref=db.backref('stripe_subscriptions', lazy=True))
    journalist = db.relationship('UserAccount', foreign_keys=[journalist_user_id], backref=db.backref('stripe_subscribers', lazy=True))

    def to_dict(self):
        return {
            'id': self.id,
            'subscriber_user_id': self.subscriber_user_id,
            'journalist_user_id': self.journalist_user_id,
            'stripe_subscription_id': self.stripe_subscription_id,
            'stripe_customer_id': self.stripe_customer_id,
            'status': self.status,
            'current_period_start': self.current_period_start.isoformat() if self.current_period_start else None,
            'current_period_end': self.current_period_end.isoformat() if self.current_period_end else None,
            'cancel_at_period_end': self.cancel_at_period_end,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


class StripePlatformRevenue(db.Model):
    """Tracks platform fees for admin dashboard"""
    __tablename__ = 'stripe_platform_revenue'

    id = db.Column(db.Integer, primary_key=True)
    period_start = db.Column(db.Date, nullable=False)
    period_end = db.Column(db.Date, nullable=False)
    total_revenue_cents = db.Column(db.Integer, default=0, nullable=False)  # Total subscriptions processed
    platform_fee_cents = db.Column(db.Integer, default=0, nullable=False)  # 10% collected
    subscription_count = db.Column(db.Integer, default=0, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now(timezone.utc))

    def to_dict(self):
        return {
            'id': self.id,
            'period_start': self.period_start.isoformat() if self.period_start else None,
            'period_end': self.period_end.isoformat() if self.period_end else None,
            'total_revenue_cents': self.total_revenue_cents,
            'total_revenue_display': f"${self.total_revenue_cents / 100:.2f}",
            'platform_fee_cents': self.platform_fee_cents,
            'platform_fee_display': f"${self.platform_fee_cents / 100:.2f}",
            'subscription_count': self.subscription_count,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class NewsletterDigestQueue(db.Model):
    """Queue for newsletters to be sent as part of a weekly digest email"""
    __tablename__ = 'newsletter_digest_queue'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user_accounts.id'), nullable=False)
    newsletter_id = db.Column(db.Integer, db.ForeignKey('newsletters.id'), nullable=False)
    week_key = db.Column(db.String(20), nullable=False)  # e.g., '2025-W48' for grouping
    queued_at = db.Column(db.DateTime, default=datetime.now(timezone.utc), nullable=False)
    sent = db.Column(db.Boolean, default=False, nullable=False)
    sent_at = db.Column(db.DateTime, nullable=True)

    __table_args__ = (
        db.UniqueConstraint('user_id', 'newsletter_id', name='uq_digest_queue_user_newsletter'),
        db.Index('ix_digest_queue_week_sent', 'week_key', 'sent'),
    )

    # Relationships
    user = db.relationship('UserAccount', backref=db.backref('digest_queue', lazy=True))
    newsletter = db.relationship('Newsletter', backref=db.backref('digest_queue_entries', lazy=True))

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'newsletter_id': self.newsletter_id,
            'week_key': self.week_key,
            'queued_at': self.queued_at.isoformat() if self.queued_at else None,
            'sent': self.sent,
            'sent_at': self.sent_at.isoformat() if self.sent_at else None,
        }
