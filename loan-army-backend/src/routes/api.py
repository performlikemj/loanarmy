from flask import Blueprint, request, jsonify, make_response, render_template, Response
from src.models.league import db, League, Team, LoanedPlayer, Newsletter, UserSubscription, EmailToken
from src.api_football_client import APIFootballClient
from datetime import datetime, date, timedelta, timezone
import uuid
import json
import logging
import csv
import io
import os
from functools import wraps
import time
from datetime import timedelta
from typing import Any

logger = logging.getLogger(__name__)

api_bp = Blueprint('api', __name__)

# Initialize API-Football client
api_client = APIFootballClient()

# API Key Authentication Decorator
def require_api_key(f):
    """Decorator to require API key for admin endpoints with optional IP whitelisting."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        client_ip = get_client_ip()
        
        # Check IP whitelist if configured
        if ALLOWED_ADMIN_IPS and client_ip not in ALLOWED_ADMIN_IPS:
            logger.warning(f"Admin access denied for IP {client_ip} (not in whitelist)")
            return jsonify({
                'error': 'Access denied from this IP address',
                'message': 'Your IP is not authorized for admin operations'
            }), 403
        
        # Get the API key from environment
        required_api_key = os.getenv('ADMIN_API_KEY')
        
        if not required_api_key:
            logger.warning("ADMIN_API_KEY not configured in environment")
            return jsonify({
                'error': 'API authentication not configured',
                'message': 'Contact administrator'
            }), 500
        
        # Get API key from request headers
        provided_key = request.headers.get('X-API-Key') or request.headers.get('Authorization')
        
        # Handle Authorization header format: "Bearer <key>" or "ApiKey <key>"
        if provided_key and provided_key.startswith(('Bearer ', 'ApiKey ')):
            provided_key = provided_key.split(' ', 1)[1]
        
        if not provided_key:
            logger.warning(f"API key missing from {client_ip}")
            return jsonify({
                'error': 'API key required',
                'message': 'Provide API key in X-API-Key header or Authorization header'
            }), 401
        
        if provided_key != required_api_key:
            logger.warning(f"Invalid API key attempt from {client_ip}")
            return jsonify({
                'error': 'Invalid API key',
                'message': 'Access denied'
            }), 403
        
        # Log successful admin access
        logger.info(f"Admin API access granted to {client_ip} for {request.endpoint}")
        return f(*args, **kwargs)
    
    return decorated_function

# CORS support
@api_bp.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization,X-API-Key')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response

@api_bp.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'api_version': '1.3.0',
        'features': {
            'transfer_windows': True,
            'window_key_support': True,
            'backward_compatibility': True,
            'team_name_resolution': True,
            'enhanced_loan_detection': True,
            'outbound_loan_sweep': True,
            'csv_table_split': True
        }
    })

@api_bp.route('/options', methods=['OPTIONS'])
def handle_options():
    return '', 200

@api_bp.route('/auth/status', methods=['GET'])
def auth_status():
    """Get API authentication status and instructions."""
    api_key_configured = bool(os.getenv('ADMIN_API_KEY'))
    ip_whitelist_configured = bool(ALLOWED_ADMIN_IPS)
    client_ip = get_client_ip()
    
    return jsonify({
        'api_key_configured': api_key_configured,
        'ip_whitelist_configured': ip_whitelist_configured,
        'client_ip': client_ip,
        'ip_whitelisted': not ip_whitelist_configured or client_ip in ALLOWED_ADMIN_IPS,
        'message': 'API key authentication is configured' if api_key_configured else 'API key authentication not configured',
        'security_status': {
            'api_key': 'configured' if api_key_configured else 'missing',
            'ip_whitelist': f'{len(ALLOWED_ADMIN_IPS)} IPs allowed' if ip_whitelist_configured else 'disabled',
            'production_ready': api_key_configured
        },
        'secured_endpoints': [
            'POST /api/players',
            'POST /api/loans', 
            'POST /api/loans/bulk-upload',
            'PUT /api/loans/<id>/performance',
            'POST /api/loans/<id>/terminate',
            'POST /api/sync-leagues',
            'POST /api/sync-teams',
            'POST /api/sync-loans',
            'POST /api/detect-loan-candidates',
            'GET /api/loan-candidates/review',
            'GET /api/export-loan-candidates/csv',
            'POST /api/import-verified-loans/csv',
            'GET /api/analyze-player-transfers/<id>',
            'GET /api/teams/<id>/analyze-loans'
        ],
        'public_endpoints': [
            'GET /api/loans/csv-template',
            'All GET endpoints for viewing data'
        ],
        'usage': {
            'header_options': [
                'X-API-Key: <your-api-key>',
                'Authorization: Bearer <your-api-key>',
                'Authorization: ApiKey <your-api-key>'
            ],
            'production_setup': [
                '1. Generate API key locally (not on server)',
                '2. Set ADMIN_API_KEY in production environment variables',
                '3. Optionally set ADMIN_IP_WHITELIST for IP restrictions',
                '4. Exclude generate_api_key.py from deployment',
                '5. Use HTTPS in production'
            ]
        }
    })

# In api.py
@api_bp.route('/newsletters/generate-weekly-all', methods=['POST'])
@require_api_key
def generate_weekly_all():
    try:
        data = request.get_json() or {}
        target_date_str = data.get('target_date')  # YYYY-MM-DD
        from datetime import datetime
        if target_date_str:
            target_dt = datetime.strptime(target_date_str, "%Y-%m-%d").date()
        else:
            target_dt = date.today()
        from src.jobs.run_weekly_newsletters import run_for_date
        result = run_for_date(target_dt)
        return jsonify({"ran_for": target_dt.isoformat(), "results": result})
    except Exception as e:
        logger.exception("generate-weekly-all failed")
        return jsonify({"error": str(e)}), 500

@api_bp.route('/newsletters/generate-weekly-all-mcp', methods=['POST'])
@require_api_key
def generate_weekly_all_mcp():
    try:
        payload = request.get_json() or {}
        target_date = payload.get('target_date')
        from datetime import datetime, date as d
        tdate = datetime.strptime(target_date, "%Y-%m-%d").date() if target_date else d.today()

        from src.jobs.run_weekly_newsletters_mcp import run_for_date
        result = run_for_date(tdate)
        return jsonify({"ran_for": tdate.isoformat(), "results": result})
    except Exception as e:
        logger.exception("generate-weekly-all-mcp failed")
        return jsonify({"error": str(e)}), 500
    
def _sync_season(window_key: str | None = None, season: int | None = None):
    """Set api_client season and prime cache. Returns the start-year int."""
    if window_key:
        season_start = int(window_key.split("::")[0].split("-")[0])
        api_client.set_season_from_window_key(window_key)
    elif season is not None:
        season_start = season
        api_client.set_season_year(season_start)
    else:
        raise ValueError("Either window_key or season required")
    api_client._prime_team_cache(season_start)
    return season_start

# Production Security Configuration
ALLOWED_ADMIN_IPS = [ip.strip() for ip in os.getenv('ADMIN_IP_WHITELIST', '').split(',') if ip.strip()]

def get_client_ip():
    """Get the real client IP, handling proxies and load balancers."""
    # Check X-Forwarded-For header (from load balancers, proxies)
    forwarded_for = request.headers.get('X-Forwarded-For')
    if forwarded_for:
        # Take the first IP in the chain (original client)
        return forwarded_for.split(',')[0].strip()
    
    # Check X-Real-IP header (nginx proxy)
    real_ip = request.headers.get('X-Real-IP')
    if real_ip:
        return real_ip.strip()
    
    # Fall back to direct connection IP
    return request.remote_addr


# League endpoints
@api_bp.route('/leagues', methods=['GET'])
def get_leagues():
    """Get all European leagues."""
    try:
        leagues = League.query.filter_by(is_european_top_league=True).all()
        return jsonify([league.to_dict() for league in leagues])
    except Exception as e:
        return jsonify({'error': str(e)}), 500



# Team endpoints
@api_bp.route('/teams', methods=['GET'])
def get_teams():
    """Get all teams with optional filtering."""
    try:
        logger.info("🏟️ GET /teams endpoint called")
        logger.info(f"📋 Request args: {dict(request.args)}")
        
        # Check database connection and teams table
        total_teams = Team.query.count()
        logger.info(f"📊 Total teams in database: {total_teams}")
        
        # Start with base query for active teams
        query = Team.query.filter_by(is_active=True)
        
        # Handle season filter
        season = request.args.get('season', type=int)
        if season:
            logger.info(f"🏆 Filtering for season: {season}")
            query = query.filter_by(season=season)
        
        # Handle european_only filter
        european_only = request.args.get('european_only', '').lower() == 'true'
        if european_only:
            logger.info("🌍 Filtering for European teams only")
            # European leagues: Premier League, La Liga, Serie A, Bundesliga, Ligue 1
            european_leagues = ['Premier League', 'La Liga', 'Serie A', 'Bundesliga', 'Ligue 1']
            query = query.join(League).filter(League.name.in_(european_leagues))
        
        # Handle has_loans filter
        has_loans = request.args.get('has_loans', '').lower() == 'true'
        if has_loans:
            logger.info("⚽ Filtering for teams with active loans")
            # Join with LoanedPlayer and filter for teams that have active loans
            query = query.join(LoanedPlayer, Team.id == LoanedPlayer.primary_team_id)\
                        .filter(LoanedPlayer.is_active == True)\
                        .distinct()
        
        teams = query.all()
        active_teams_count = len(teams)
        logger.info(f"✅ Filtered teams found: {active_teams_count}")
        
        if active_teams_count == 0:
            logger.warning("⚠️ No teams found matching the filters")
            # If user asked for European-only teams and none are in DB, lazily sync minimal data for current season
            if european_only:
                try:
                    season = season or api_client.current_season_start_year
                    logger.info(f"🔁 Attempting lazy sync for European top leagues for season {season}")
                    # Sync leagues (top-5)
                    leagues_data = api_client.get_european_leagues(season)
                    for league_data in leagues_data:
                        league_info = league_data.get('league', {})
                        country_info = league_data.get('country', {})
                        seasons = league_data.get('seasons', [])
                        current_season = next((s for s in seasons if s.get('current')), seasons[0] if seasons else {})
                        existing = League.query.filter_by(league_id=league_info.get('id')).first()
                        if existing:
                            existing.name = league_info.get('name')
                            existing.country = country_info.get('name')
                            existing.season = current_season.get('year', api_client.current_season_start_year)
                            existing.logo = league_info.get('logo')
                            existing.is_european_top_league = True
                        else:
                            db.session.add(League(
                                league_id=league_info.get('id'),
                                name=league_info.get('name'),
                                country=country_info.get('name'),
                                season=current_season.get('year', api_client.current_season_start_year),
                                is_european_top_league=True,
                                logo=league_info.get('logo')
                            ))
                    # Sync teams for those leagues
                    all_teams = api_client.get_all_european_teams(season)
                    for team_data in all_teams:
                        team_info = team_data.get('team', {})
                        league_info = team_data.get('league_info', {})
                        league = League.query.filter_by(league_id=league_info.get('id')).first()
                        if not league:
                            continue
                        existing_team = Team.query.filter_by(team_id=team_info.get('id'), season=season).first()
                        if existing_team:
                            existing_team.name = team_info.get('name')
                            existing_team.country = team_info.get('country')
                            existing_team.founded = team_info.get('founded')
                            existing_team.logo = team_info.get('logo')
                            existing_team.league_id = league.id
                            existing_team.is_active = True
                        else:
                            db.session.add(Team(
                                team_id=team_info.get('id'),
                                name=team_info.get('name'),
                                country=team_info.get('country'),
                                founded=team_info.get('founded'),
                                logo=team_info.get('logo'),
                                league_id=league.id,
                                season=season,
                                is_active=True
                            ))
                    db.session.commit()
                    logger.info("✅ Lazy sync complete, refetching teams")
                    # Re-run the filtered query
                    query = Team.query.filter_by(is_active=True)
                    if season:
                        query = query.filter_by(season=season)
                    if european_only:
                        european_leagues = ['Premier League', 'La Liga', 'Serie A', 'Bundesliga', 'Ligue 1']
                        query = query.join(League).filter(League.name.in_(european_leagues))
                    teams = query.all()
                    active_teams_count = len(teams)
                except Exception as sync_ex:
                    logger.error(f"Lazy sync failed: {sync_ex}")
            
        team_dicts = [team.to_dict() for team in teams]
        logger.info(f"📤 Returning {len(team_dicts)} team records")
        
        return jsonify(team_dicts)
    except Exception as e:
        logger.error(f"❌ Error in get_teams: {str(e)}")
        logger.error(f"❌ Exception type: {type(e).__name__}")
        import traceback
        logger.error(f"❌ Traceback: {traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500

@api_bp.route('/teams/<int:team_id>', methods=['GET'])
def get_team(team_id):
    """Get specific team with loan details."""
    try:
        team = Team.query.get_or_404(team_id)
        team_dict = team.to_dict()
        
        # Add detailed loan information
        active_loans = LoanedPlayer.query.filter_by(
            primary_team_id=team.id, 
            is_active=True
        ).all()
        
        team_dict['active_loans'] = [loan.to_dict() for loan in active_loans]
        
        return jsonify(team_dict)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@api_bp.route('/teams/<int:team_id>/loans', methods=['GET'])
def get_team_loans(team_id):
    """Get loans for a specific team."""
    try:
        team = Team.query.get_or_404(team_id)
        loans = LoanedPlayer.query.filter_by(primary_team_id=team.id).all()
        return jsonify([loan.to_dict() for loan in loans])
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@api_bp.route('/teams/<int:team_id>/loans/season/<season>', methods=['GET'])
def get_team_loans_by_season(team_id, season):
    """Get loans for a specific team in a specific season."""
    try:
        team = Team.query.get_or_404(team_id)
        loans = LoanedPlayer.query.filter_by(
            primary_team_id=team.id,
            loan_season=season
        ).all()
        return jsonify([loan.to_dict() for loan in loans])
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@api_bp.route('/teams/season/<int:season>', methods=['GET'])
def get_teams_for_season(season):
    """Get all teams for a specific season with their names."""
    try:
        team_mapping = api_client.get_teams_for_season(season)
        return jsonify({
            'season': season,
            'teams': team_mapping,
            'count': len(team_mapping)
        })
    except Exception as e:
        logger.error(f"Error fetching teams for season {season}: {e}")
        return jsonify({'error': str(e)}), 500

@api_bp.route('/teams/<int:team_id>/api-info', methods=['GET'])
def get_team_api_info(team_id):
    """Get team information from API-Football by ID."""
    try:
        season = request.args.get('season', api_client.current_season_start_year)
        team_data = api_client.get_team_by_id(team_id)
        
        if not team_data:
            return jsonify({'error': f'Team {team_id} not found'}), 404
            
        return jsonify({
            'team_id': team_id,
            'season': season,
            'data': team_data
        })
    except Exception as e:
        logger.error(f"Error fetching team {team_id} from API: {e}")
        return jsonify({'error': str(e)}), 500

def resolve_team_ids(id_or_api_id: int, season: int = None) -> tuple[int | None, int | None, str | None]:
    """
    Return (db_id, api_id, name) for a team, accepting either a DB PK or an
    API-Football team_id.  We prefer an API-id match first, then DB PK.
    If season is provided, it will be used to filter the team lookup.
    """
    # 1 – exact API-id match (with season if provided)
    if season:
        row = Team.query.filter_by(team_id=id_or_api_id, season=season).first()
    else:
        row = Team.query.filter_by(team_id=id_or_api_id).first()
    if row:
        return row.id, row.team_id, row.name

    # 2 – fallback: treat as DB primary-key
    row = Team.query.get(id_or_api_id)
    if row:
        return row.id, row.team_id, row.name

    # 3 – not found
    return None, None, None

# Loan endpoints
@api_bp.route('/loans', methods=['GET'])
def get_loans():
    """Get all loans with optional filters."""
    try:
        query = LoanedPlayer.query
        
        # Filter by season
        season = request.args.get('season')
        if season:
            query = query.filter_by(loan_season=season)
        
        # Filter by active status
        active_only = request.args.get('active_only', 'false').lower() == 'true'
        if active_only:
            query = query.filter_by(is_active=True)
        
        # Filter by loan type
        loan_type = request.args.get('loan_type')
        if loan_type:
            query = query.filter_by(loan_type=loan_type)
        
        # Filter by early termination
        early_termination = request.args.get('early_termination')
        if early_termination is not None:
            query = query.filter_by(early_termination=early_termination.lower() == 'true')
        
        loans = query.order_by(LoanedPlayer.loan_start_date.desc()).all()
        return jsonify([loan.to_dict() for loan in loans])
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@api_bp.route('/loans/active', methods=['GET'])
def get_active_loans():
    """Get active loans."""
    try:
        loans = LoanedPlayer.query.filter_by(is_active=True).all()
        return jsonify([loan.to_dict() for loan in loans])
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@api_bp.route('/loans/season/<season>', methods=['GET'])
def get_loans_by_season(season):
    """Get all loans for a specific season."""
    try:
        loans = LoanedPlayer.query.filter_by(loan_season=season).all()
        return jsonify([loan.to_dict() for loan in loans])
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ---------------------------------------------------------------------
# Weekly Loans Report Endpoint
# ---------------------------------------------------------------------
@api_bp.route('/loans/weekly-report', methods=['GET'])
@require_api_key
def weekly_loans_report():
    """
    Weekly report summarising all active loanees from a parent club.
    Query parameters:
              - primary_team_id (int)  [required]
      - season (int)          [optional, default current]
      - from (YYYY-MM-DD)     [required] week start
      - to   (YYYY-MM-DD)     [required] week end
      - include_team_stats    [optional bool] include team statistics per match
    """
    try:
        # Accept either a DB PK or an API-Football team_id for primary_team_id
        arg_team_id = request.args.get('primary_team_id', type=int)
        if not arg_team_id:
            return jsonify({'error': 'primary_team_id is required'}), 400

        season_param = request.args.get('season', type=int)
        start_str = request.args.get('from')
        end_str = request.args.get('to')
        if not start_str or not end_str:
            return jsonify({'error': "'from' and 'to' query params are required (YYYY-MM-DD)"}), 400

        try:
            week_start = datetime.strptime(start_str, '%Y-%m-%d').date()
            week_end = datetime.strptime(end_str, '%Y-%m-%d').date()
        except ValueError:
            return jsonify({'error': "Invalid 'from' or 'to' date. Use YYYY-MM-DD"}), 400

        # Infer season from 'from' date if not provided explicitly (European season starts Aug 1)
        if season_param is None:
            season = week_start.year if week_start.month >= 8 else week_start.year - 1
        else:
            season = season_param

        db_id, api_id, team_name = resolve_team_ids(arg_team_id, season)
        if not db_id:
            return jsonify({'error': f'Team {arg_team_id} not found for season {season}'}), 404

        include_team_stats = request.args.get('include_team_stats', 'false').lower() in ('true', '1', 'yes', 'y')

        # Sync season with API client & prime cache
        api_client.set_season_year(season)
        api_client._prime_team_cache(season)

        report = api_client.summarize_parent_loans_week(
            parent_team_db_id=db_id,
            parent_team_api_id=api_id,
            season=season,
            week_start=week_start,
            week_end=week_end,
            include_team_stats=include_team_stats,
            db_session=db.session,
        )

        # Overwrite parent_team for consistent shape
        report['parent_team'] = {
            'id': api_id,     # API id for clients
            'db_id': db_id,   # DB PK
            'name': team_name
        }

        # Persist fixtures / stats fetched above
        db.session.commit()

        return jsonify(report)
    except Exception as e:
        logger.error(f"Error generating weekly loans report: {e}")
        return jsonify({'error': str(e)}), 500

@api_bp.route('/loans/<int:loan_id>/terminate', methods=['POST'])
@require_api_key
def terminate_loan(loan_id):
    """Terminate a loan early."""
    try:
        loan = LoanedPlayer.query.get_or_404(loan_id)
        data = request.get_json()
        
        termination_reason = data.get('reason', 'Not specified')
        termination_date = data.get('termination_date')
        
        if termination_date:
            try:
                termination_date = datetime.strptime(termination_date, '%Y-%m-%d').date()
            except ValueError:
                return jsonify({'error': 'Invalid date format. Use YYYY-MM-DD'}), 400
        else:
            termination_date = date.today()
        
        # Update loan record
        loan.early_termination = True
        loan.termination_reason = termination_reason
        loan.termination_date = termination_date
        loan.actual_end_date = termination_date
        loan.is_active = False
        loan.updated_at = datetime.now(timezone.utc)
        
        db.session.commit()
        
        return jsonify({
            'message': 'Loan terminated successfully',
            'loan': loan.to_dict()
        })
        
    except Exception as e:
        logger.error(f"Error terminating loan: {e}")
        return jsonify({'error': str(e)}), 500

@api_bp.route('/loans/<int:loan_id>/performance', methods=['PUT'])
@require_api_key
def update_loan_performance(loan_id):
    """Update performance stats for a loan."""
    try:
        loan = LoanedPlayer.query.get_or_404(loan_id)
        data = request.get_json()
        
        # Update performance fields
        if 'appearances' in data:
            loan.appearances = data['appearances']
        if 'goals' in data:
            loan.goals = data['goals']
        if 'assists' in data:
            loan.assists = data['assists']
        if 'minutes_played' in data:
            loan.minutes_played = data['minutes_played']
        if 'performance_notes' in data:
            loan.performance_notes = data['performance_notes']
        
        loan.last_performance_update = datetime.now(timezone.utc)
        loan.updated_at = datetime.now(timezone.utc)
        
        db.session.commit()
        
        return jsonify({
            'message': 'Performance updated successfully',
            'loan': loan.to_dict()
        })
        
    except Exception as e:
        logger.error(f"Error updating performance: {e}")
        return jsonify({'error': str(e)}), 500


@api_bp.route("/reviewed-loan-candidates/upload", methods=["POST"])
@require_api_key
def upload_reviewed_loan_candidates():
    try:
        if "file" not in request.files:
            return {"error": "CSV file required"}, 400
        file = request.files["file"]
        if not file.filename.lower().endswith(".csv"):
            return {"error": "Must be a CSV"}, 400

        dry_run = request.args.get("dry_run", "false").lower() in ("true", "1", "yes", "y")

        # --- read and tidy CSV text ---
        raw = file.read().decode("utf-8", errors="ignore")
        raw = raw.replace("\r\n", "\n").replace("\r", "\n")

        # Auto‑detect delimiter (tab vs comma)
        first_line = raw.split("\n", 1)[0]
        delimiter = "\t" if first_line.count("\t") > first_line.count(",") else ","

        # If header starts with an empty first cell (leading delimiter), strip it
        if first_line.startswith(delimiter):
            raw_lines = raw.split("\n")
            raw_lines[0] = raw_lines[0].lstrip(delimiter)
            raw = "\n".join(raw_lines)

        rows = csv.DictReader(io.StringIO(raw), delimiter=delimiter, skipinitialspace=True)
        rows.fieldnames = [f.strip() for f in (rows.fieldnames or [])]
        logger.info(f"Detected delimiter: '{delimiter}' | headers: {rows.fieldnames}")

        required = {"player_id", "loan_team_id", "window_key", "is_likely_loan"}
        has_parent_alias = ("parent_team_id" in rows.fieldnames) or ("primary_team_id" in rows.fieldnames)
        if not required.issubset(set(rows.fieldnames)) or not has_parent_alias:
            return {
                "error": "Missing required columns",
                "required": "player_id, loan_team_id, window_key, is_likely_loan, and one of parent_team_id or primary_team_id"
            }, 400

        def _truthy(v):
            return str(v).strip().lower() in ("true", "1", "yes", "y")

        def _to_int(v):
            try:
                return int(str(v).strip())
            except Exception:
                return None

        def _parse_season_from_window(window_key: str):
            try:
                season_slug, _ = window_key.split("::")
                return int(season_slug.split("-")[0])  # e.g. "2022" from "2022-23::FULL"
            except Exception:
                return None

        def _ensure_team(api_team_id: int, season_start_year: int):
            """
            Ensure a Team row exists for given API team id and season.
            If missing, fetch from API-Football and insert minimal Team.
            Returns Team (DB row) or None if not resolvable.
            """
            if not api_team_id:
                return None
            t = Team.query.filter_by(team_id=api_team_id, season=season_start_year).first()
            if t:
                return t

            # Fetch from API-Football (season helps name resolution)
            tdata = api_client.get_team_by_id(api_team_id, season_start_year)
            if not tdata or "team" not in tdata:
                return None

            ti = tdata["team"] or {}
            team = Team(
                team_id=ti.get("id"),
                name=ti.get("name") or f"Team {api_team_id}",
                code=ti.get("code"),
                country=ti.get("country") or "Unknown",
                founded=ti.get("founded"),
                national=bool(ti.get("national", False)),
                logo=ti.get("logo"),
                season=season_start_year or api_client.current_season_start_year,
                is_active=True,
                league_id=None  # Optional: backfill league later if desired
            )
            db.session.add(team)
            db.session.flush()
            return team

        created, skipped, errors = [], [], []

        # Data starts on line 2 for DictReader; idx here is CSV line number
        for idx, row in enumerate(rows, start=2):
            try:
                # Skip empty/separator rows (club headings, etc.)
                if not any(v and str(v).strip() for v in row.values()):
                    continue

                # Only process rows marked as TRUE
                if not _truthy(row.get("is_likely_loan", "")):
                    skipped.append({"row": idx, "reason": "not marked TRUE"})
                    continue

                # Parse required values
                api_player_id = _to_int(row.get("player_id"))
                api_parent_id = _to_int(row.get("parent_team_id") or row.get("primary_team_id"))
                api_loan_id = _to_int(row.get("loan_team_id"))
                window_key = (row.get("window_key") or "").strip()

                if not (api_player_id and api_parent_id and api_loan_id and window_key):
                    errors.append(f"Row {idx}: missing player_id / primary_team_id / loan_team_id / window_key")
                    continue

                # Optional values from CSV (fallbacks applied below)
                player_name = (row.get("player_name") or "").strip()
                age = _to_int(row.get("age"))
                nationality = (row.get("nationality") or "").strip() or None
                primary_team_name_csv = (row.get("primary_team_name") or "").strip()
                loan_team_name_csv = (row.get("loan_team_name") or "").strip()
                team_ids_str = (row.get("team_ids") or "").strip()
                reviewer_notes = (row.get("reviewer_notes") or "").strip()

                season_start_year = _parse_season_from_window(window_key) or api_client.current_season_start_year

                # Ensure teams exist (create if missing)
                parent_team = _ensure_team(api_parent_id, season_start_year)
                if not parent_team:
                    errors.append(f"Row {idx}: parent team API id {api_parent_id} not found or not resolvable")
                    continue

                loan_team = _ensure_team(api_loan_id, season_start_year)
                if not loan_team:
                    errors.append(f"Row {idx}: loan team API id {api_loan_id} not found or not resolvable")
                    continue

                # Determine final human names
                primary_team_name = primary_team_name_csv or parent_team.name
                loan_team_name = loan_team_name_csv or loan_team.name

                # Duplicate check
                dup = LoanedPlayer.query.filter_by(
                    player_id=api_player_id,
                    primary_team_id=parent_team.id,
                    loan_team_id=loan_team.id,
                    window_key=window_key,
                    is_active=True
                ).first()
                if dup:
                    skipped.append({
                        "row": idx,
                        "reason": "duplicate (same player/teams/window_key active)",
                        "player_id": api_player_id,
                        "primary_team_id": parent_team.id,
                        "loan_team_id": loan_team.id,
                        "window_key": window_key
                    })
                    continue

                # Build record
                loan_data = dict(
                    player_id=api_player_id,  # raw API-Football ID per your current model
                    player_name=player_name or f"Player {api_player_id}",
                    age=age,
                    nationality=nationality,
                    primary_team_id=parent_team.id,
                    primary_team_name=primary_team_name,
                    loan_team_id=loan_team.id,
                    loan_team_name=loan_team_name,
                    team_ids=team_ids_str,
                    window_key=window_key,
                    reviewer_notes=reviewer_notes,
                    is_active=True
                )

                if dry_run:
                    created.append({**loan_data, "dry_run": True})
                else:
                    loan = LoanedPlayer(**loan_data)
                    db.session.add(loan)
                    created.append({
                        "player_id": api_player_id,
                        "primary_team_id": parent_team.id,
                        "loan_team_id": loan_team.id,
                        "window_key": window_key
                    })
            except Exception as ex:
                logger.exception(f"Row {idx} processing error")
                errors.append(f"Row {idx}: {ex}")

        if not dry_run and created:
            db.session.commit()

        return {
            "created_count": len(created),
            "skipped_count": len(skipped),
            "errors_count": len(errors),
            "dry_run": dry_run,
            "created": created[:5],
            "skipped": skipped[:5],
            "errors": errors[:5],
        }, 201 if created and not dry_run else 200

    except Exception as e:
        logger.exception("Unhandled error in reviewed-loan-candidates/upload")
        return {"error": str(e)}, 500

@api_bp.route('/loans/csv-template', methods=['GET'])
def get_csv_template():
    """Download CSV template for bulk loan upload."""
    try:
        # Create CSV template with headers and example data
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write headers
        headers = [
            'player_id', 'parent_team_id', 'loan_team_id', 'loan_start_date', 'loan_season',
            'loan_end_date', 'loan_type', 'loan_fee', 'buy_option_fee', 'recall_option',
            'appearances', 'goals', 'assists', 'minutes_played', 'performance_notes'
        ]
        writer.writerow(headers)
        
        # Write example rows
        writer.writerow([
            '1001', '33', '532', '2024-08-15', '2024-25',
            '2025-06-30', 'Season Long', '5000000', '25000000', 'true',
            '15', '3', '2', '1200', 'Performing well at Valencia'
        ])
        writer.writerow([
            '1002', '33', '165', '2025-01-15', '2024-25',
            '2025-06-30', 'Half Season', '', '15000000', 'true',
            '8', '1', '4', '650', 'Good impact since joining Dortmund'
        ])
        
        output.seek(0)
        csv_content = output.getvalue()
        output.close()
        
        from flask import Response
        return Response(
            csv_content,
            mimetype='text/csv',
            headers={'Content-Disposition': 'attachment; filename=loan_upload_template.csv'}
        )
        
    except Exception as e:
        logger.error(f"Error generating CSV template: {e}")
        return jsonify({'error': str(e)}), 500

# Newsletter endpoints
@api_bp.route('/newsletters', methods=['GET'])
def get_newsletters():
    """Get newsletters with filters."""
    try:
        query = Newsletter.query
        
        # Filter by team
        team_id = request.args.get('team')
        if team_id:
            query = query.filter_by(team_id=team_id)
        
        # Filter by newsletter type
        newsletter_type = request.args.get('type')
        if newsletter_type:
            query = query.filter_by(newsletter_type=newsletter_type)
        
        # Filter by published status
        published_only = request.args.get('published_only', 'false').lower() == 'true'
        if published_only:
            query = query.filter_by(published=True)
        
        # Filter by date range
        days = request.args.get('days')
        if days:
            try:
                cutoff_date = datetime.utcnow() - timedelta(days=int(days))
                query = query.filter(Newsletter.generated_date >= cutoff_date)
            except ValueError:
                pass

        # Filter by a specific week range (inclusive)
        # Expect week_start and week_end as YYYY-MM-DD
        week_start_str = request.args.get('week_start')
        week_end_str = request.args.get('week_end')
        if week_start_str and week_end_str:
            try:
                week_start = datetime.strptime(week_start_str, '%Y-%m-%d').date()
                week_end = datetime.strptime(week_end_str, '%Y-%m-%d').date()
                # Match newsletters whose stored week range overlaps the requested week
                query = query.filter(
                    db.and_(
                        Newsletter.week_start_date <= week_end,
                        Newsletter.week_end_date >= week_start,
                    )
                )
            except ValueError:
                pass

        # Exclude current week (server-side)
        exclude_current_week = request.args.get('exclude_current_week', 'false').lower() in ('true', '1', 'yes', 'y')
        if exclude_current_week:
            today = date.today()
            # Compute Monday..Sunday of current week
            days_since_monday = today.weekday()
            current_week_start = today - timedelta(days=days_since_monday)
            current_week_end = current_week_start + timedelta(days=6)
            # Exclude if generated/published in current week OR stored week overlaps current week
            query = query.filter(
                db.and_(
                    db.or_(
                        Newsletter.published_date == None,
                        db.not_(db.and_(
                            db.func.date(Newsletter.published_date) >= current_week_start,
                            db.func.date(Newsletter.published_date) <= current_week_end,
                        )),
                    ),
                    db.or_(
                        Newsletter.week_start_date == None,
                        Newsletter.week_end_date == None,
                        db.not_(db.and_(
                            Newsletter.week_start_date <= current_week_end,
                            Newsletter.week_end_date >= current_week_start,
                        )),
                    ),
                )
            )
        
        newsletters = query.order_by(Newsletter.generated_date.desc()).all()
        return jsonify([newsletter.to_dict() for newsletter in newsletters])
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@api_bp.route('/newsletters/<int:newsletter_id>', methods=['GET'])
def get_newsletter(newsletter_id):
    """Get specific newsletter."""
    try:
        newsletter = Newsletter.query.get_or_404(newsletter_id)
        payload = newsletter.to_dict()
        # Extract embedded rendered variants if present
        try:
            obj = json.loads(payload.get('structured_content') or payload.get('content') or '{}')
            rendered = obj.get('rendered') if isinstance(obj, dict) else None
            if isinstance(rendered, dict):
                payload['rendered'] = {
                    k: (v if isinstance(v, str) else '') for k, v in rendered.items()
                }
        except Exception:
            pass
        return jsonify(payload)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@api_bp.route('/newsletters/generate', methods=['POST'])
def generate_newsletter():
    """Generate a newsletter for a specific team and date."""
    try:
        data = request.get_json()
        team_id = data.get('team_id')
        target_date = data.get('target_date')  # Format: YYYY-MM-DD
        newsletter_type = data.get('type', 'weekly')
        
        if not team_id:
            return jsonify({'error': 'team_id is required'}), 400
        
        team = Team.query.get_or_404(team_id)
        
        # Parse target date
        if target_date:
            try:
                target_date = datetime.strptime(target_date, '%Y-%m-%d').date()
            except ValueError:
                return jsonify({'error': 'Invalid date format. Use YYYY-MM-DD'}), 400
        else:
            target_date = date.today()
        
        # Check if newsletter already exists for this team and date
        existing = Newsletter.query.filter_by(
            team_id=team_id,
            newsletter_type=newsletter_type,
            issue_date=target_date
        ).first()
        
        if existing:
            return jsonify({
                'message': 'Newsletter already exists for this date',
                'newsletter': existing.to_dict()
            })
        
        # Get loan data for the target date (season-based)
        current_season = api_client.current_season
        loans = LoanedPlayer.query.filter_by(
            parent_team_id=team_id,
            loan_season=current_season
        ).all()
        
        # Calculate week start and end dates for weekly newsletters
        if newsletter_type == 'weekly':
            # Get the Monday of the week containing target_date
            days_since_monday = target_date.weekday()
            week_start_date = target_date - timedelta(days=days_since_monday)
            week_end_date = week_start_date + timedelta(days=6)
        else:
            week_start_date = target_date
            week_end_date = target_date
        
        # Generate newsletter content using AI (mock implementation)
        newsletter_content = generate_newsletter_content(team, loans, target_date, newsletter_type)
        
        # Create newsletter record
        newsletter = Newsletter(
            team_id=team_id,
            newsletter_type=newsletter_type,
            title=json.loads(newsletter_content)['title'],
            content=newsletter_content,
            issue_date=target_date,
            week_start_date=week_start_date,
            week_end_date=week_end_date,
            generated_date=datetime.utcnow(),
            published=True,
            published_date=datetime.utcnow()
        )
        
        db.session.add(newsletter)
        db.session.commit()
        
        return jsonify({
            'message': 'Newsletter generated successfully',
            'newsletter': newsletter.to_dict()
        })
        
    except Exception as e:
        logger.error(f"Error generating newsletter: {e}")
        return jsonify({'error': str(e)}), 500

def generate_newsletter_content(team, loans, target_date, newsletter_type):
    """Generate AI-powered newsletter content with season context."""
    # Mock implementation - in real version, this would use OpenAI API
    active_loans = [loan for loan in loans if loan.is_active]
    terminated_loans = [loan for loan in loans if not loan.is_active]
    
    content = {
        'title': f'{team.name} Loan Update - {target_date.strftime("%B %d, %Y")}',
        'summary': f'Season {api_client.current_season} update on {team.name}\'s loan activities.',
        'season': api_client.current_season,
        'sections': []
    }
    
    if active_loans:
        content['sections'].append({
            'title': 'Active Loans',
            'content': f'{len(active_loans)} players currently out on loan'
        })
        
        for loan in active_loans:
            performance_summary = f"{loan.appearances} appearances"
            if loan.goals > 0:
                performance_summary += f", {loan.goals} goals"
            if loan.assists > 0:
                performance_summary += f", {loan.assists} assists"
            
            content['sections'].append({
                'player_name': loan.player_name,
                'loan_team': loan.loan_team_name,
                'status': 'Active loan',
                'performance': performance_summary,
                'analysis': f'Player showing {"excellent" if loan.goals > 3 else "good" if loan.appearances > 10 else "steady"} progress at {loan.loan_team_name}.'
            })
    
    if not active_loans:
        content['sections'].append({
            'title': 'No Current Loans',
            'content': f'{team.name} currently has no players out on loan for the {api_client.current_season} season.'
        })
    
    return json.dumps(content)

# Subscription endpoints
@api_bp.route('/subscriptions', methods=['GET'])
@require_api_key
def get_subscriptions():
    """Admin: list subscriptions with optional active filter."""
    try:
        active_only = request.args.get('active_only', 'false').lower() in ('true', '1', 'yes', 'y')
        query = UserSubscription.query
        if active_only:
            query = query.filter(UserSubscription.active == True)
        subscriptions = query.all()
        return jsonify([sub.to_dict() for sub in subscriptions])
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@api_bp.route('/subscriptions', methods=['POST'])
def create_subscription():
    """Create a new subscription for a single team."""
    try:
        data = request.get_json() or {}

        email = data.get('email')
        team_id = data.get('team_id')
        preferred_frequency = data.get('preferred_frequency', 'weekly')

        if not email or not team_id:
            return jsonify({'error': 'email and team_id are required'}), 400

        team = Team.query.get_or_404(int(team_id))

        existing = UserSubscription.query.filter_by(email=email, team_id=team.id).first()
        if existing:
            # Reactivate/update existing subscription
            existing.active = True
            existing.preferred_frequency = preferred_frequency
            if not existing.unsubscribe_token:
                existing.unsubscribe_token = str(uuid.uuid4())
            db.session.commit()
            return jsonify({
                'message': 'Subscription already existed and was updated',
                'subscription': existing.to_dict()
            }), 200

        subscription = UserSubscription(
            email=email,
            team_id=team.id,
            preferred_frequency=preferred_frequency,
            active=True,
            unsubscribe_token=str(uuid.uuid4()),
        )
        
        db.session.add(subscription)
        db.session.commit()
        
        return jsonify({
            'message': 'Subscription created successfully',
            'subscription': subscription.to_dict()
        }), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@api_bp.route('/subscriptions/bulk_create', methods=['POST'])
def bulk_create_subscriptions():
    """Create or update subscriptions for multiple teams in one request."""
    try:
        data = request.get_json() or {}
        email = data.get('email')
        team_ids = data.get('team_ids') or []
        preferred_frequency = data.get('preferred_frequency', 'weekly')

        if not email or not team_ids:
            return jsonify({'error': 'email and team_ids are required'}), 400

        created_ids: list[int] = []
        updated_ids: list[int] = []
        skipped: list[dict] = []

        for raw_id in team_ids:
            try:
                tid = int(raw_id)
            except Exception:
                skipped.append({'team_id': raw_id, 'reason': 'invalid team id'})
                continue

            team = Team.query.get(tid)
            if not team:
                skipped.append({'team_id': tid, 'reason': 'team not found'})
                continue

            existing = UserSubscription.query.filter_by(email=email, team_id=team.id).first()
            if existing:
                if not existing.active or existing.preferred_frequency != preferred_frequency:
                    existing.active = True
                    existing.preferred_frequency = preferred_frequency
                    if not existing.unsubscribe_token:
                        existing.unsubscribe_token = str(uuid.uuid4())
                    updated_ids.append(existing.id)
                else:
                    skipped.append({'team_id': team.id, 'reason': 'already active'})
                continue

            sub = UserSubscription(
                email=email,
                team_id=team.id,
                preferred_frequency=preferred_frequency,
                active=True,
                unsubscribe_token=str(uuid.uuid4()),
            )
            db.session.add(sub)
            db.session.flush()
            created_ids.append(sub.id)

        db.session.commit()

        result_ids = created_ids + updated_ids
        subs = UserSubscription.query.filter(UserSubscription.id.in_(result_ids)).all() if result_ids else []

        return jsonify({
            'message': f'Processed {len(team_ids)} team(s)',
            'created_count': len(created_ids),
            'updated_count': len(updated_ids),
            'skipped_count': len(skipped),
            'created_ids': created_ids,
            'updated_ids': updated_ids,
            'skipped': skipped,
            'subscriptions': [s.to_dict() for s in subs]
        }), 201 if created_ids else 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

def _create_email_token(email: str, purpose: str, metadata: dict | None = None, ttl_minutes: int = 60) -> EmailToken:
    token = str(uuid.uuid4())
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=ttl_minutes)
    row = EmailToken(
        token=token,
        email=email,
        purpose=purpose,
        expires_at=expires_at,
        metadata_json=json.dumps(metadata or {})
    )
    db.session.add(row)
    db.session.flush()
    return row

@api_bp.route('/subscriptions/request-manage-link', methods=['POST'])
def request_manage_link():
    """Issue a one-time manage token emailed to the user (email delivery handled elsewhere)."""
    try:
        data = request.get_json() or {}
        email = data.get('email')
        if not email:
            return jsonify({'error': 'email is required'}), 400
        # 30 days TTL so links in newsletters remain useful across sends
        tok = _create_email_token(email=email, purpose='manage', ttl_minutes=60 * 24 * 30)
        db.session.commit()
        return jsonify({'message': 'Manage link created', 'token': tok.token, 'expires_at': tok.expires_at.isoformat()})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@api_bp.route('/subscriptions/manage/<token>', methods=['GET'])
def get_manage_state(token: str):
    """Validate token and return current subscriptions for that email."""
    try:
        row = EmailToken.query.filter_by(token=token, purpose='manage').first()
        if not row or not row.is_valid():
            return jsonify({'error': 'invalid or expired token'}), 400
        subs = UserSubscription.query.filter_by(email=row.email, active=True).all()
        return jsonify({'email': row.email, 'subscriptions': [s.to_dict() for s in subs], 'expires_at': row.expires_at.isoformat()})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@api_bp.route('/subscriptions/manage/<token>', methods=['POST'])
def update_manage_state(token: str):
    """Upsert subscriptions for the token's email using team_ids and preferred_frequency."""
    try:
        row = EmailToken.query.filter_by(token=token, purpose='manage').first()
        if not row or not row.is_valid():
            return jsonify({'error': 'invalid or expired token'}), 400

        payload = request.get_json() or {}
        team_ids = payload.get('team_ids') or []
        preferred_frequency = payload.get('preferred_frequency', 'weekly')

        # Deactivate all current subscriptions for this email first
        UserSubscription.query.filter_by(email=row.email, active=True).update({UserSubscription.active: False})

        # Activate/create for provided list
        for raw_id in team_ids:
            team = Team.query.get(int(raw_id))
            if not team:
                continue
            existing = UserSubscription.query.filter_by(email=row.email, team_id=team.id).first()
            if existing:
                existing.active = True
                existing.preferred_frequency = preferred_frequency
                if not existing.unsubscribe_token:
                    existing.unsubscribe_token = str(uuid.uuid4())
            else:
                db.session.add(UserSubscription(
                    email=row.email,
                    team_id=team.id,
                    preferred_frequency=preferred_frequency,
                    active=True,
                    unsubscribe_token=str(uuid.uuid4()),
                ))

        # Optionally mark token as used immediately or let it remain valid until expiry
        # row.used_at = datetime.now(timezone.utc)

        db.session.commit()
        return jsonify({'message': 'Subscriptions updated'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@api_bp.route('/subscriptions/unsubscribe/<token>', methods=['POST'])
def token_unsubscribe(token: str):
    """Unsubscribe a single subscription by its unsubscribe token."""
    try:
        sub = UserSubscription.query.filter_by(unsubscribe_token=token).first()
        if not sub:
            return jsonify({'error': 'invalid token'}), 404
        sub.active = False
        db.session.commit()
        return jsonify({'message': 'Unsubscribed successfully'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@api_bp.route('/verify/request', methods=['POST'])
def request_verification_token():
    """Issue a verification token for confirming email ownership."""
    try:
        data = request.get_json() or {}
        email = data.get('email')
        if not email:
            return jsonify({'error': 'email is required'}), 400
        # 48 hours TTL for verification
        tok = _create_email_token(email=email, purpose='verify', ttl_minutes=60 * 24 * 2)
        db.session.commit()
        return jsonify({'message': 'Verification token created', 'token': tok.token, 'expires_at': tok.expires_at.isoformat()})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@api_bp.route('/verify/<token>', methods=['POST'])
def verify_email_token(token: str):
    """Mark verification token as used and return success if valid."""
    try:
        row = EmailToken.query.filter_by(token=token, purpose='verify').first()
        if not row or not row.is_valid():
            return jsonify({'error': 'invalid or expired token'}), 400
        row.used_at = datetime.now(timezone.utc)
        db.session.commit()
        return jsonify({'message': 'Email verified', 'email': row.email})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@api_bp.route('/subscriptions/<int:subscription_id>', methods=['DELETE'])
def delete_subscription(subscription_id):
    """Unsubscribe from newsletter."""
    try:
        subscription = UserSubscription.query.get_or_404(subscription_id)
        subscription.active = False
        db.session.commit()
        
        return jsonify({'message': 'Unsubscribed successfully'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Statistics endpoints
@api_bp.route('/stats/overview', methods=['GET'])
def get_overview_stats():
    """Get overview statistics."""
    try:
        current_season = api_client.current_season
        
        stats = {
            'total_teams': Team.query.filter_by(is_active=True).count(),
            'european_leagues': League.query.filter_by(is_european_top_league=True).count(),
            'total_active_loans': LoanedPlayer.query.filter_by(is_active=True).count(),
            'season_loans': LoanedPlayer.query.filter_by(loan_season=current_season).count(),
            'early_terminations': LoanedPlayer.query.filter_by(early_termination=True, loan_season=current_season).count(),
            'teams_with_loans': db.session.query(LoanedPlayer.parent_team_id).filter_by(is_active=True).distinct().count(),
            'total_subscriptions': UserSubscription.query.filter_by(is_active=True).count(),
            'total_newsletters': Newsletter.query.filter_by(published=True).count(),
            'current_season': current_season
        }
        return jsonify(stats)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@api_bp.route('/stats/loans', methods=['GET'])
def get_loan_stats():
    """Get detailed loan statistics."""
    try:
        current_season = api_client.current_season
        
        # Loan type breakdown
        loan_types = db.session.query(
            LoanedPlayer.loan_type,
            db.func.count(LoanedPlayer.id).label('count')
        ).filter_by(loan_season=current_season).group_by(LoanedPlayer.loan_type).all()
        
        # Termination reasons
        termination_reasons = db.session.query(
            LoanedPlayer.termination_reason,
            db.func.count(LoanedPlayer.id).label('count')
        ).filter_by(early_termination=True, loan_season=current_season).group_by(LoanedPlayer.termination_reason).all()
        
        stats = {
            'current_season': current_season,
            'loan_types': [{'type': lt[0], 'count': lt[1]} for lt in loan_types],
            'termination_reasons': [{'reason': tr[0], 'count': tr[1]} for tr in termination_reasons if tr[0]],
            'total_season_loans': LoanedPlayer.query.filter_by(loan_season=current_season).count(),
            'active_loans': LoanedPlayer.query.filter_by(loan_season=current_season, is_active=True).count(),
            'completed_loans': LoanedPlayer.query.filter_by(loan_season=current_season, is_active=False, early_termination=False).count(),
            'early_terminations': LoanedPlayer.query.filter_by(loan_season=current_season, early_termination=True).count()
        }
        
        return jsonify(stats)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Data sync endpoints
@api_bp.route('/init-data', methods=['POST'])
def init_data():
    """Initialize sample data."""
    try:
        # This would normally sync from API-Football
        # For now, just return success
        return jsonify({
            'message': 'Data initialized successfully',
            'teams_synced': Team.query.count(),
            'leagues_synced': League.query.count()
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@api_bp.route('/sync-leagues', methods=['POST'])
@require_api_key
def sync_leagues():
    """Sync European leagues from API-Football."""
    try:
        # Use current season for league sync (league metadata doesn't change much)
        season = api_client.current_season_start_year
        leagues_data = api_client.get_european_leagues(season)
        synced_count = 0
        
        for league_data in leagues_data:
            league_info = league_data.get('league', {})
            country_info = league_data.get('country', {})
            seasons = league_data.get('seasons', [])
            current_season = next((s for s in seasons if s.get('current')), seasons[0] if seasons else {})
            
            # Check if league exists
            existing = League.query.filter_by(league_id=league_info.get('id')).first()
            if existing:
                # Update existing league
                existing.name = league_info.get('name')
                existing.country = country_info.get('name')
                existing.season = current_season.get('year', api_client.current_season_start_year)
                existing.logo = league_info.get('logo')
            else:
                # Create new league
                league = League(
                    league_id=league_info.get('id'),
                    name=league_info.get('name'),
                    country=country_info.get('name'),
                    season=current_season.get('year', api_client.current_season_start_year),
                    is_european_top_league=True,
                    logo=league_info.get('logo')
                )
                db.session.add(league)
            
            synced_count += 1
        
        db.session.commit()
        return jsonify({
            'message': f'Successfully synced {synced_count} European leagues',
            'synced_leagues': synced_count,
            'current_season': api_client.current_season
        })
        
    except Exception as e:
        logger.error(f"Error syncing leagues: {e}")
        return jsonify({'error': str(e)}), 500

@api_bp.route('/sync-teams/<int:season>', methods=['POST'])
@require_api_key
def sync_teams(season):
    """Sync teams from API-Football."""
    try:
        # season is provided as path parameter by Flask
        if not season:
            return jsonify({'error': 'Season parameter is required'}), 400
            
        # Get all European teams
        all_teams = api_client.get_all_european_teams(season)
        synced_count = 0
        
        for team_data in all_teams:
            team_info = team_data.get('team', {})
            league_info = team_data.get('league_info', {})
            
            # Find the league
            league = League.query.filter_by(league_id=league_info.get('id')).first()
            if not league:
                continue
            
            # Check if team exists for this season
            existing = Team.query.filter_by(team_id=team_info.get('id'), season=season).first()
            if existing:
                # Update existing team
                existing.name = team_info.get('name')
                existing.country = team_info.get('country')
                existing.founded = team_info.get('founded')
                existing.logo = team_info.get('logo')
                existing.league_id = league.id
            else:
                # Create new team for this season
                team = Team(
                    team_id=team_info.get('id'),
                    name=team_info.get('name'),
                    country=team_info.get('country'),
                    founded=team_info.get('founded'),
                    logo=team_info.get('logo'),
                    league_id=league.id,
                    season=season,
                    is_active=True
                )
                db.session.add(team)
            
            synced_count += 1
        
        db.session.commit()
        return jsonify({
            'message': f'Successfully synced {synced_count} teams from European leagues for season {season}',
            'synced_teams': synced_count,
            'season': season
        })
        
    except Exception as e:
        logger.error(f"Error syncing teams: {e}")
        return jsonify({'error': str(e)}), 500

# Loan Detection Endpoints

@api_bp.route('/detect-loan-candidates', methods=['POST'])
@require_api_key
def detect_loan_candidates():
    """Detect players who appear in multiple teams (potential loans)."""
    try:
        data = request.get_json() or {}
        print(f'detect_loan_candidates data: {data}')
        season = int(request.json["season"])
        _sync_season(season=season)
        
        # Default to Top-5 European leagues as recommended
        league_ids = data.get('league_ids', [39, 140, 78, 135, 61])  
        
        logger.info(f"🔍 Starting loan candidate detection for season {season}")
        
        # Use the new league-level crawler to detect multi-team players
        multi_team_dict = api_client.detect_multi_team_players(
            league_ids=league_ids, 
            season=season
        )

        loan_candidates = []
        processed_count = 0
        
        for player_id, team_ids in multi_team_dict.items():
            try:
                # Get player info - we need to fetch this separately now
                player_data = api_client.get_player_by_id(player_id)

                if not player_data or 'player' not in player_data:
                    logger.warning(f"Could not fetch player info for {player_id}")
                    continue
                player_info = player_data['player']

                # Analyze transfer data using the pre-computed multi-team data
                transfer_analysis = api_client.analyze_transfer_type(
                    player_id, 
                    multi_team_dict=multi_team_dict, 
                    season=season
                )

                # Create comprehensive candidate profile
                loan_candidate = {
                    'player_id': player_id,
                    'player_name': player_info.get('name'),
                    'team_ids': team_ids,
                    'team_count': len(team_ids),
                    'season': season,
                    'transfer_analysis': transfer_analysis,
                    'loan_confidence': transfer_analysis.get('loan_confidence', 0.5),
                    'is_likely_loan': transfer_analysis.get('is_likely_loan', False),
                    'indicators': transfer_analysis.get('indicators', []),
                    'needs_review': True,
                    'detected_at': datetime.utcnow().isoformat()
                }

                loan_candidates.append(loan_candidate)
                processed_count += 1
                
                # Update player record if it exists
                existing_player = LoanedPlayer.query.filter_by(player_id=player_id).first()
                if existing_player:
                    # Don't override existing manual settings, just flag for review
                    if not hasattr(existing_player, 'loan_review_needed'):
                        # Add a simple flag - you might want to add this field to your model
                        pass
                        
            except Exception as e:
                logger.warning(f"Error processing player {player_id}: {e}")
                continue
        
        logger.info(f"✅ Detected {len(loan_candidates)} loan candidates")
        
        return jsonify({
            'message': f'Successfully detected {len(loan_candidates)} loan candidates',
            'candidates': loan_candidates,
            'total_candidates': len(loan_candidates),
            'season': season,
            'processed_players': processed_count
        })
        
    except Exception as e:
        logger.error(f"Error detecting loan candidates: {e}")
        return jsonify({'error': str(e)}), 500


@api_bp.route('/export-loan-candidates/csv', methods=['GET'])
@require_api_key
def export_loan_candidates_csv():
    """Export detected loan candidates to CSV for manual verification."""
    try:
        warnings = []
        
        window_key = request.args.get("window_key")
        confidence_threshold = float(request.args.get("confidence_threshold", 0.4))
        season = _sync_season(window_key=window_key)
        league_ids = request.args.getlist('league_ids', type=int)
        
        if not league_ids:
            league_ids = [39, 140, 78, 135, 61]  # Default to Top-5 European leagues
        
        # Extract season from window_key for consistent API calls  
        try:
            season = int(window_key.split("::")[0].split("-")[0])
            logger.info(f"🔍 window {window_key} → season {season}")
        except (ValueError, IndexError):
            season = api_client.current_season_start_year
            logger.warning(f"Failed to parse season from window_key '{window_key}', using default: {season}")
        
        logger.info(f"📊 Exporting loan candidates for window {window_key} (confidence ≥ {confidence_threshold})")
        
        # Set API client season from window_key to ensure consistency
        api_client.set_season_from_window_key(window_key)
        
        # Prime team name cache for efficient lookups
        api_client._prime_team_cache(season)
        
        # Method 1: Get direct loan candidates from transfer data (bypasses confidence threshold)
        direct_loan_candidates = api_client.get_direct_loan_candidates(
            window_key, league_ids, season=season
        )
        
        # Method 2: Get multi-team players using the new window-based method
        multi_team_dict = api_client.detect_multi_team_players(
            league_ids, window_key, season=season
        )
        
        logger.info(f"🔍 DEBUG: Found {len(direct_loan_candidates)} direct loan candidates and {len(multi_team_dict)} multi-team players for window {window_key}")
        
        candidates = []
        processed = 0
        
        # First, add all direct loan candidates (these have loan_confidence = 1.0)
        for player_id, loan_data in direct_loan_candidates.items():
            try:
                # Get player info
                player_data = api_client.get_player_by_id(player_id)
                if not player_data or 'player' not in player_data:
                    continue
                
                player_info = player_data['player']
                
                # Create candidate from direct loan data
                candidate = {
                    'player_id': player_id,
                    'player_name': player_info.get('name', 'Unknown'),
                    'age': player_info.get('age', ''),
                    'nationality': player_info.get('nationality', 'Unknown'),
                    'primary_team_id': loan_data.get('primary_team_id', ''),
                    'primary_team_name': loan_data.get('primary_team_name', 'Unknown'),
                    'loan_team_id': loan_data.get('loan_team_id', ''),
                    'loan_team_name': loan_data.get('loan_team_name', 'Unknown'),
                    'team_ids': loan_data.get('team_ids', ''),
                    'team_count': loan_data.get('team_count', 2),
                    'loan_confidence': loan_data.get('loan_confidence', 1.0),
                    'is_likely_loan': True,
                    'indicators': f"Direct loan transfer on {loan_data.get('transfer_date', 'unknown date')}",
                    'window_key': window_key,
                    'detected_at': datetime.now(timezone.utc).isoformat(),
                    # Fields for manual verification (empty for reviewer to fill)
                    'manual_verified': '',
                    'actual_loan_status': '',
                    'legacy_parent_team_id': '',  # Legacy field - keeping for backward compatibility
                    'legacy_loan_team_id': '',    # Legacy field - keeping for backward compatibility
                    'reviewer_notes': ''
                }
                candidates.append(candidate)
                processed += 1
                

                    
            except Exception as e:
                logger.warning(f"Error processing direct loan candidate {player_id}: {e}")
                continue
        
        # Second, process multi-team players that aren't already captured as direct loans
        direct_loan_player_ids = set(direct_loan_candidates.keys())
        
        for player_id, team_ids in multi_team_dict.items():
            # Skip players already processed as direct loans
            if player_id in direct_loan_player_ids:
                logger.debug(f"Skipping player {player_id} - already processed as direct loan")
                continue
                
            try:
                # Get player info
                player_data = api_client.get_player_by_id(player_id)
                if not player_data or 'player' not in player_data:
                    continue

                player_info = player_data['player']
                
                # Get transfer analysis using pre-computed multi-team data
                transfer_analysis = api_client.analyze_transfer_type(
                    player_id, 
                    multi_team_dict=multi_team_dict, 
                    window_key=window_key
                )
                
                loan_confidence = transfer_analysis.get('loan_confidence', 0.0)
                

                
                # Only include candidates above confidence threshold
                if loan_confidence >= confidence_threshold:
                    # Extract season year from window_key for team name lookup
                    try:
                        season_slug, _ = window_key.split("::")
                        season_year = int(season_slug.split("-")[0])
                    except (ValueError, AttributeError):
                        season_year = api_client.current_season_start_year
                    
                    # Split team IDs according to new schema: [loan_team_id, primary_team_id]
                    loan_team_id, primary_team_id = (team_ids + [None, None])[:2]
                    
                    # Get human-readable team names
                    primary_team_name = "Unknown"
                    loan_team_name = "Unknown"
                    
                    if primary_team_id:
                        primary_team_name = api_client.get_team_name(primary_team_id, season_year)
                    if loan_team_id:
                        loan_team_name = api_client.get_team_name(loan_team_id, season_year)
                    
                    candidate = {
                        'player_id': player_id,
                        'player_name': player_info.get('name', 'Unknown'),
                        'age': player_info.get('age', ''),
                        'nationality': player_info.get('nationality', 'Unknown'),
                        'primary_team_id': primary_team_id or '',
                        'primary_team_name': primary_team_name,
                        'loan_team_id': loan_team_id or '',
                        'loan_team_name': loan_team_name,
                        'team_ids': ','.join(map(str, team_ids)),  # Keep for backward compatibility
                        'team_count': len(team_ids),
                        'loan_confidence': round(loan_confidence, 3),
                        'is_likely_loan': transfer_analysis.get('is_likely_loan', False),
                        'indicators': ' | '.join(transfer_analysis.get('indicators', [])),
                        'window_key': window_key,
                        'detected_at': datetime.now(timezone.utc).isoformat(),
                        # Fields for manual verification (empty for reviewer to fill)
                        'manual_verified': '',
                        'actual_loan_status': '',  # 'loan', 'permanent', 'unknown'
                        'legacy_parent_team_id': '',  # Legacy field - keeping for backward compatibility
                        'legacy_loan_team_id': '',    # Legacy field - keeping for backward compatibility
                        'reviewer_notes': ''
                    }
                    
                    candidates.append(candidate)
                    processed += 1
                    
            except Exception as e:
                logger.warning(f"Error processing player {player_id}: {e}")
                continue
        
        # Sort by confidence (highest first)
        candidates.sort(key=lambda x: x['loan_confidence'], reverse=True)
        
        direct_loan_count = len(direct_loan_candidates)
        multi_team_processed = len(multi_team_dict) - len(direct_loan_player_ids)
        
        logger.info(f"🔍 DEBUG: Final results - {len(candidates)} total candidates")
        logger.info(f"   - {direct_loan_count} direct loan transfers (confidence = 1.0)")
        logger.info(f"   - {len(candidates) - direct_loan_count} from multi-team analysis (≥ {confidence_threshold} confidence)")
        logger.info(f"   - {multi_team_processed} multi-team players analyzed (excluding direct loans)")
        
        if not candidates:
            logger.warning(f"❌ No loan candidates found. Direct loans: {direct_loan_count}, Multi-team players: {len(multi_team_dict)}, Threshold: {confidence_threshold}")
            return jsonify({'message': 'No loan candidates found matching criteria'}), 404
        
        # Create CSV content
        output = io.StringIO()
        fieldnames = [
            'player_id','player_name','age','nationality',
            'primary_team_id','primary_team_name','loan_team_id','loan_team_name',
            'team_ids','team_count','loan_confidence','is_likely_loan',
            'indicators','window_key','detected_at',
            'manual_verified','actual_loan_status',
            'legacy_parent_team_id','legacy_loan_team_id','reviewer_notes'
        ]
        
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(candidates)
        
        csv_content = output.getvalue()
        output.close()
        
        # Generate filename
        timestamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
        # Use window_key for filename but clean it up for filesystem compatibility
        window_safe = window_key.replace("::", "_")
        filename = f"loan_candidates_{window_safe}_{timestamp}.csv"
        
        logger.info(f"✅ Exported {len(candidates)} loan candidates for {window_key} ({direct_loan_count} direct loans + {len(candidates) - direct_loan_count} multi-team)")
        
        response = make_response(
            csv_content,
            200,
            {
                'Content-Type': 'text/csv',
                'Content-Disposition': f'attachment; filename={filename}'
            }
        )
        
        # Add deprecation warning header if using legacy season parameter
        if warnings:
            response.headers['X-Deprecation-Warning'] = '; '.join(warnings)
        
        return response
        
    except Exception as e:
        logger.error(f"Error exporting loan candidates CSV: {e}")
        return jsonify({'error': str(e)}), 500

# Newsletter rendering helpers
try:
    # Reuse lint/enrich if available via weekly agent
    from src.agents.weekly_agent import lint_and_enrich  # type: ignore
except Exception:
    def lint_and_enrich(x: dict) -> dict:  # fallback
        return x


def _load_newsletter_json(n: Newsletter) -> dict | None:
    try:
        raw = n.structured_content or n.content or "{}"
        data = json.loads(raw)
        if isinstance(data, dict):
            try:
                data = lint_and_enrich(data)
            except Exception:
                pass
            return data
        return None
    except Exception:
        return None


def _plain_text_from_news(data: dict, meta: Newsletter) -> str:
    team = meta.team.name if meta.team else ""
    title = data.get("title") or meta.title or "Weekly Loan Update"
    rng = data.get("range") or [None, None]
    summary = data.get("summary") or ""
    lines: list[str] = []
    lines.append(f"{title}")
    if team:
        lines.append(f"Team: {team}")
    if rng and rng[0] and rng[1]:
        lines.append(f"Week: {rng[0]} – {rng[1]}")
    if summary:
        lines.append("")
        lines.append(summary)
    highlights = data.get("highlights") or []
    if highlights:
        lines.append("")
        lines.append("Highlights:")
        for h in highlights:
            lines.append(f"- {h}")
    for sec in (data.get("sections") or []):
        st = sec.get("title") or ""
        items = sec.get("items") or []
        if st:
            lines.append("")
            lines.append(st)
            lines.append("-" * len(st))
        for it in items:
            pname = it.get("player_name") or ""
            loan_team = it.get("loan_team") or it.get("loan_team_name") or ""
            wsum = it.get("week_summary") or ""
            stats = it.get("stats") or {}
            stat_str = (
                f"{int(stats.get('minutes', 0))}’ | "
                f"{int(stats.get('goals', 0))}G {int(stats.get('assists', 0))}A | "
                f"{int(stats.get('yellows', 0))}Y {int(stats.get('reds', 0))}R"
            )
            lines.append(f"• {pname} ({loan_team}) – {wsum}")
            lines.append(f"  {stat_str}")
            notes = it.get("match_notes") or []
            for n in notes:
                lines.append(f"  - {n}")
    return "\n".join(lines).strip() + "\n"


@api_bp.route('/newsletters/<int:newsletter_id>/render.<fmt>', methods=['GET'])
@require_api_key
def render_newsletter(newsletter_id: int, fmt: str):
    try:
        n = Newsletter.query.get_or_404(newsletter_id)
        data = _load_newsletter_json(n) or {}
        context: dict[str, Any] = {
            'meta': n,
            'team_name': n.team.name if n.team else '',
            'title': data.get('title') or n.title,
            'range': data.get('range'),
            'summary': data.get('summary'),
            'highlights': data.get('highlights') or [],
            'sections': data.get('sections') or [],
            'by_numbers': data.get('by_numbers') or {},
            'fan_pulse': data.get('fan_pulse') or [],
        }
        if fmt in ('html', 'web'):
            html = render_template('newsletter_web.html', **context)
            return Response(html, mimetype='text/html')
        if fmt in ('email', 'email.html'):
            html = render_template('newsletter_email.html', **context)
            return Response(html, mimetype='text/html')
        if fmt in ('txt', 'text'):
            text = _plain_text_from_news(data, n)
            return Response(text, mimetype='text/plain; charset=utf-8')
        return jsonify({'error': 'Unsupported format. Use html, email, or text'}), 400
    except Exception as e:
        logger.exception('Error rendering newsletter')
        return jsonify({'error': str(e)}), 500


@api_bp.route('/newsletters/latest/render.<fmt>', methods=['GET'])
@require_api_key
def render_latest_newsletter(fmt: str):
    try:
        team_id = request.args.get('team', type=int)
        if not team_id:
            return jsonify({'error': 'team query param required'}), 400
        n = (
            Newsletter.query
            .filter_by(team_id=team_id)
            .order_by(Newsletter.generated_date.desc())
            .first()
        )
        if not n:
            return jsonify({'error': 'No newsletters found for team'}), 404
        return render_newsletter(n.id, fmt)
    except Exception as e:
        logger.exception('Error rendering latest newsletter')
        return jsonify({'error': str(e)}), 500

@api_bp.route('/newsletters/generate-weekly-mcp-team', methods=['POST'])
@require_api_key
def generate_weekly_mcp_team():
    try:
        payload = request.get_json() or {}
        target_date = payload.get('target_date')
        team_db_id = payload.get('team_db_id')
        api_team_id = payload.get('api_team_id')
        if not (team_db_id or api_team_id):
            return jsonify({'error': 'team_db_id or api_team_id is required'}), 400
        from datetime import datetime, date as d
        tdate = datetime.strptime(target_date, "%Y-%m-%d").date() if target_date else d.today()

        # Resolve DB id if only API id provided (use inferred season from date)
        if not team_db_id and api_team_id:
            season = tdate.year if tdate.month >= 8 else tdate.year - 1
            row = Team.query.filter_by(team_id=int(api_team_id), season=season).first()
            if not row:
                return jsonify({'error': f'Team api_id={api_team_id} not found for season {season}'}), 404
            team_db_id = row.id
        from src.agents.weekly_agent import generate_weekly_newsletter_with_mcp_sync
        out = generate_weekly_newsletter_with_mcp_sync(int(team_db_id), tdate)
        return jsonify({'team_db_id': team_db_id, 'ran_for': tdate.isoformat(), 'result': out})
    except Exception as e:
        logger.exception("generate-weekly-mcp-team failed")
        return jsonify({'error': str(e)}), 500

# --- Guest loan flag endpoints ---
from src.models.league import LoanFlag

@api_bp.route('/loans/flags', methods=['POST'])
def create_loan_flag():
    try:
        data = request.get_json() or {}
        required = ('player_id', 'primary_team_api_id', 'reason')
        missing = [k for k in required if not str(data.get(k, '')).strip()]
        if missing:
            return jsonify({'error': f"Missing required: {', '.join(missing)}"}), 400
        lf = LoanFlag(
            player_api_id=int(data['player_id']),
            primary_team_api_id=int(data['primary_team_api_id']),
            loan_team_api_id=(int(data['loan_team_api_id']) if data.get('loan_team_api_id') else None),
            season=(int(data['season']) if data.get('season') else None),
            reason=str(data['reason']).strip(),
            email=(str(data.get('email')).strip() or None),
            ip_address=get_client_ip(),
            user_agent=request.headers.get('User-Agent')[:512] if request.headers.get('User-Agent') else None,
            status='pending'
        )
        db.session.add(lf)
        db.session.commit()
        return jsonify({'message': 'Flag submitted', 'id': lf.id}), 201
    except Exception as e:
        logger.exception('Error creating loan flag')
        return jsonify({'error': str(e)}), 500

@api_bp.route('/loans/flags/pending', methods=['GET'])
@require_api_key
def list_pending_flags():
    try:
        rows = LoanFlag.query.filter_by(status='pending').order_by(LoanFlag.created_at.desc()).all()
        return jsonify([{
            'id': r.id,
            'player_api_id': r.player_api_id,
            'primary_team_api_id': r.primary_team_api_id,
            'loan_team_api_id': r.loan_team_api_id,
            'season': r.season,
            'reason': r.reason,
            'email': r.email,
            'created_at': r.created_at.isoformat() if r.created_at else None
        } for r in rows])
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@api_bp.route('/loans/flags/<int:flag_id>/resolve', methods=['POST'])
@require_api_key
def resolve_flag(flag_id: int):
    try:
        row = LoanFlag.query.get_or_404(flag_id)
        data = request.get_json() or {}
        action = (data.get('action') or '').strip()
        note = (data.get('note') or '').strip()

        # Optional: deactivate corresponding loan if requested
        deactivated = 0
        if action == 'deactivate_loan':
            season = row.season
            # Map API ids to Team DB ids
            parent_team = Team.query.filter_by(team_id=row.primary_team_api_id, season=season).first()
            loan_team = Team.query.filter_by(team_id=row.loan_team_api_id, season=season).first() if row.loan_team_api_id else None
            q = LoanedPlayer.query.filter(LoanedPlayer.player_id == row.player_api_id)
            if parent_team:
                q = q.filter(LoanedPlayer.primary_team_id == parent_team.id)
            if loan_team:
                q = q.filter(LoanedPlayer.loan_team_id == loan_team.id)
            for loan in q.all():
                loan.is_active = False
                deactivated += 1
            db.session.commit()
        row.status = 'resolved'
        row.admin_note = note or row.admin_note
        from datetime import datetime as _dt, timezone as _tz
        row.resolved_at = _dt.now(_tz.utc)
        db.session.commit()
        return jsonify({'message': 'Flag resolved', 'deactivated_loans': deactivated})
    except Exception as e:
        logger.exception('Error resolving loan flag')
        return jsonify({'error': str(e)}), 500
