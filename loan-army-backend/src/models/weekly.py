from datetime import datetime, timezone
from src.models.league import db

# ------------------------------------------------------------------
# 📊 WEEKLY REPORT / FIXTURE PERSISTENCE TABLES
# ------------------------------------------------------------------

class WeeklyLoanReport(db.Model):
    __tablename__ = 'weekly_loan_reports'
    id = db.Column(db.Integer, primary_key=True)
    parent_team_id = db.Column(db.Integer, db.ForeignKey('teams.id'), nullable=False)
    parent_team_api_id = db.Column(db.Integer, nullable=False)
    season = db.Column(db.Integer, nullable=False)
    week_start_date = db.Column(db.Date, nullable=False)
    week_end_date = db.Column(db.Date, nullable=False)
    include_team_stats = db.Column(db.Boolean, default=False)
    generated_at = db.Column(db.DateTime, default=datetime.now(timezone.utc))
    meta_json = db.Column(db.Text)
    __table_args__ = (
        db.UniqueConstraint('parent_team_id', 'week_start_date', 'week_end_date',
                            name='uq_weekly_parent_week'),
    )


class Fixture(db.Model):
    __tablename__ = 'fixtures'
    id = db.Column(db.Integer, primary_key=True)
    fixture_id_api = db.Column(db.Integer, unique=True, nullable=False)
    date_utc = db.Column(db.DateTime)
    season = db.Column(db.Integer, nullable=False)
    competition_name = db.Column(db.String(100))
    home_team_api_id = db.Column(db.Integer)
    away_team_api_id = db.Column(db.Integer)
    home_goals = db.Column(db.Integer, default=0)
    away_goals = db.Column(db.Integer, default=0)
    raw_json = db.Column(db.Text)


class FixtureTeamStats(db.Model):
    __tablename__ = 'fixture_team_stats'
    id = db.Column(db.Integer, primary_key=True)
    fixture_id = db.Column(db.Integer, db.ForeignKey('fixtures.id'), nullable=False)
    team_api_id = db.Column(db.Integer, nullable=False)
    stats_json = db.Column(db.Text)
    __table_args__ = (
        db.UniqueConstraint('fixture_id', 'team_api_id', name='uq_fixture_team'),
    )


class FixturePlayerStats(db.Model):
    __tablename__ = 'fixture_player_stats'
    id = db.Column(db.Integer, primary_key=True)
    fixture_id = db.Column(db.Integer, db.ForeignKey('fixtures.id'), nullable=False)
    player_api_id = db.Column(db.Integer, nullable=False)
    team_api_id = db.Column(db.Integer, nullable=False)
    minutes = db.Column(db.Integer, default=0)
    goals = db.Column(db.Integer, default=0)
    assists = db.Column(db.Integer, default=0)
    yellows = db.Column(db.Integer, default=0)
    reds = db.Column(db.Integer, default=0)
    raw_json = db.Column(db.Text)
    __table_args__ = (
        db.UniqueConstraint('fixture_id', 'player_api_id',
                            name='uq_fixture_player'),
    )


class WeeklyLoanAppearance(db.Model):
    __tablename__ = 'weekly_loan_appearances'
    id = db.Column(db.Integer, primary_key=True)
    weekly_report_id = db.Column(db.Integer,
                                 db.ForeignKey('weekly_loan_reports.id'),
                                 nullable=False)
    loaned_player_id = db.Column(db.Integer,
                                 db.ForeignKey('loaned_players.id'),
                                 nullable=False)
    player_api_id = db.Column(db.Integer, nullable=False)
    fixture_id = db.Column(db.Integer, db.ForeignKey('fixtures.id'),
                           nullable=False)
    team_api_id = db.Column(db.Integer, nullable=False)
    appeared = db.Column(db.Boolean, default=False)
    minutes = db.Column(db.Integer, default=0)
    goals = db.Column(db.Integer, default=0)
    assists = db.Column(db.Integer, default=0)
    yellows = db.Column(db.Integer, default=0)
    reds = db.Column(db.Integer, default=0)
    __table_args__ = (
        db.UniqueConstraint('weekly_report_id', 'loaned_player_id',
                            'fixture_id', name='uq_week_player_fixture'),
    )

