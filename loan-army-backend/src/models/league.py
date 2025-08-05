from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

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
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
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

class Team(db.Model):
    __tablename__ = 'teams'
    
    id = db.Column(db.Integer, primary_key=True)
    team_id = db.Column(db.Integer, unique=True, nullable=False)
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
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    season = db.Column(db.Integer, unique=True, nullable=False)
    
    # Relationships
    loaned_out_players = db.relationship('LoanedPlayer', 
                                       foreign_keys='LoanedPlayer.parent_team_id',
                                       backref='parent_team', lazy=True)
    loaned_in_players = db.relationship('LoanedPlayer',
                                      foreign_keys='LoanedPlayer.loan_team_id', 
                                      backref='loan_team', lazy=True)
    newsletters = db.relationship('Newsletter', backref='team', lazy=True)
    subscriptions = db.relationship('UserSubscription', backref='team', lazy=True)
    
    def to_dict(self):
        current_loans = [loan for loan in self.loaned_out_players if loan.is_active]
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
            'league_name': self.league.name if self.league else None,
            'current_loaned_out_count': len(current_loans),
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

class Player(db.Model):
    __tablename__ = 'players'
    
    id = db.Column(db.Integer, primary_key=True)
    player_id = db.Column(db.Integer, unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    firstname = db.Column(db.String(50))
    lastname = db.Column(db.String(50))
    age = db.Column(db.Integer)
    birth_date = db.Column(db.Date)
    birth_place = db.Column(db.String(100))
    birth_country = db.Column(db.String(50))
    nationality = db.Column(db.String(50))
    height = db.Column(db.String(10))
    weight = db.Column(db.String(10))
    injured = db.Column(db.Boolean, default=False)
    photo = db.Column(db.String(255))
    position = db.Column(db.String(20))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    loans = db.relationship('LoanedPlayer', backref='player', lazy=True)
    
    @property
    def current_age(self):
        if self.birth_date:
            from datetime import date
            today = date.today()
            return today.year - self.birth_date.year - ((today.month, today.day) < (self.birth_date.month, self.birth_date.day))
        return self.age
    
    def to_dict(self):
        return {
            'id': self.id,
            'player_id': self.player_id,
            'name': self.name,
            'firstname': self.firstname,
            'lastname': self.lastname,
            'age': self.age,
            'current_age': self.current_age,
            'birth_date': self.birth_date.isoformat() if self.birth_date else None,
            'birth_place': self.birth_place,
            'birth_country': self.birth_country,
            'nationality': self.nationality,
            'height': self.height,
            'weight': self.weight,
            'injured': self.injured,
            'photo': self.photo,
            'position': self.position,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

class LoanedPlayer(db.Model):
    __tablename__ = 'loaned_players'
    
    id = db.Column(db.Integer, primary_key=True)
    player_id = db.Column(db.Integer, db.ForeignKey('players.id'), nullable=False)
    parent_team_id = db.Column(db.Integer, db.ForeignKey('teams.id'), nullable=False)
    loan_team_id = db.Column(db.Integer, db.ForeignKey('teams.id'), nullable=False)
    loan_start_date = db.Column(db.Date, nullable=False)
    loan_end_date = db.Column(db.Date)
    original_end_date = db.Column(db.Date)  # Original planned end date
    actual_end_date = db.Column(db.Date)    # Actual end date if terminated early
    loan_fee = db.Column(db.Float)
    buy_option_fee = db.Column(db.Float)
    buy_option_deadline = db.Column(db.Date)
    is_active = db.Column(db.Boolean, default=True)
    loan_type = db.Column(db.String(50), default='Season Long')  # Season Long, Half Season, Emergency, etc.
    loan_season = db.Column(db.String(10))  # e.g., "2024-25"
    early_termination = db.Column(db.Boolean, default=False)
    termination_reason = db.Column(db.String(200))  # Injury, Recall, Poor Performance, etc.
    termination_date = db.Column(db.Date)
    recall_option = db.Column(db.Boolean, default=True)  # Can parent club recall?
    performance_notes = db.Column(db.Text)
    last_performance_update = db.Column(db.DateTime)
    appearances = db.Column(db.Integer, default=0)
    goals = db.Column(db.Integer, default=0)
    assists = db.Column(db.Integer, default=0)
    minutes_played = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'player_id': self.player_id,
            'player_name': self.player.name if self.player else None,
            'parent_team_id': self.parent_team_id,
            'parent_team_name': self.parent_team.name if self.parent_team else None,
            'loan_team_id': self.loan_team_id,
            'loan_team_name': self.loan_team.name if self.loan_team else None,
            'loan_start_date': self.loan_start_date.isoformat() if self.loan_start_date else None,
            'loan_end_date': self.loan_end_date.isoformat() if self.loan_end_date else None,
            'original_end_date': self.original_end_date.isoformat() if self.original_end_date else None,
            'actual_end_date': self.actual_end_date.isoformat() if self.actual_end_date else None,
            'loan_fee': self.loan_fee,
            'buy_option_fee': self.buy_option_fee,
            'buy_option_deadline': self.buy_option_deadline.isoformat() if self.buy_option_deadline else None,
            'is_active': self.is_active,
            'loan_type': self.loan_type,
            'loan_season': self.loan_season,
            'early_termination': self.early_termination,
            'termination_reason': self.termination_reason,
            'termination_date': self.termination_date.isoformat() if self.termination_date else None,
            'recall_option': self.recall_option,
            'performance_notes': self.performance_notes,
            'last_performance_update': self.last_performance_update.isoformat() if self.last_performance_update else None,
            'appearances': self.appearances,
            'goals': self.goals,
            'assists': self.assists,
            'minutes_played': self.minutes_played,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
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
    published = db.Column(db.Boolean, default=False)
    published_date = db.Column(db.DateTime)
    email_sent = db.Column(db.Boolean, default=False)
    email_sent_date = db.Column(db.DateTime)
    subscriber_count = db.Column(db.Integer, default=0)
    generated_date = db.Column(db.DateTime, default=datetime.utcnow)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
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
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
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

