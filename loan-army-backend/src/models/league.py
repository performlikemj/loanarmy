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
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
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
    created_at = db.Column(db.DateTime, default=datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=datetime.now(timezone.utc), onupdate=datetime.now(timezone.utc))
    last_login_at = db.Column(db.DateTime)
    last_display_name_change_at = db.Column(db.DateTime)

    comments = db.relationship('NewsletterComment', back_populates='user', lazy=True)

    def to_dict(self):
        return {
            'id': self.id,
            'email': sanitize_plain_text(self.email) if self.email else None,
            'display_name': sanitize_plain_text(self.display_name) if self.display_name else None,
            'display_name_confirmed': bool(self.display_name_confirmed),
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'last_login_at': self.last_login_at.isoformat() if self.last_login_at else None,
            'last_display_name_change_at': self.last_display_name_change_at.isoformat() if self.last_display_name_change_at else None,
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
    __tablename__ = 'newsletter_player_youtube_links'

    id = db.Column(db.Integer, primary_key=True)
    newsletter_id = db.Column(db.Integer, db.ForeignKey('newsletters.id', ondelete='CASCADE'), nullable=False)
    player_id = db.Column(db.Integer, nullable=True)  # API-Football player ID for tracked players
    supplemental_loan_id = db.Column(db.Integer, db.ForeignKey('supplemental_loans.id', ondelete='CASCADE'), nullable=True)
    player_name = db.Column(db.String(120), nullable=False)
    youtube_link = db.Column(db.String(500), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=datetime.now(timezone.utc), onupdate=datetime.now(timezone.utc))

    newsletter = db.relationship('Newsletter', backref='youtube_links', lazy=True)
    supplemental_loan = db.relationship('SupplementalLoan', lazy=True)

    def to_dict(self):
        return {
            'id': self.id,
            'newsletter_id': self.newsletter_id,
            'player_id': self.player_id,
            'supplemental_loan_id': self.supplemental_loan_id,
            'player_name': self.player_name,
            'youtube_link': self.youtube_link,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }
