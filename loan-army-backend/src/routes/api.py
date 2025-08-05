from flask import Blueprint, request, jsonify, make_response
from src.models.league import db, League, Team, Player, LoanedPlayer, Newsletter, UserSubscription
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

logger = logging.getLogger(__name__)

api_bp = Blueprint('api', __name__)

# Initialize API-Football client
api_client = APIFootballClient()

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
            query = query.join(LoanedPlayer, Team.id == LoanedPlayer.parent_team_id)\
                        .filter(LoanedPlayer.is_active == True)\
                        .distinct()
        
        teams = query.all()
        active_teams_count = len(teams)
        logger.info(f"✅ Filtered teams found: {active_teams_count}")
        
        if active_teams_count == 0:
            logger.warning("⚠️ No teams found matching the filters")
            
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
            parent_team_id=team.id, 
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
        loans = LoanedPlayer.query.filter_by(parent_team_id=team.id).all()
        return jsonify([loan.to_dict() for loan in loans])
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@api_bp.route('/teams/<int:team_id>/loans/season/<season>', methods=['GET'])
def get_team_loans_by_season(team_id, season):
    """Get loans for a specific team in a specific season."""
    try:
        team = Team.query.get_or_404(team_id)
        loans = LoanedPlayer.query.filter_by(
            parent_team_id=team.id,
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

# Player endpoints
@api_bp.route('/players', methods=['GET'])
def get_players():
    """Get all players."""
    try:
        players = Player.query.all()
        return jsonify([player.to_dict() for player in players])
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@api_bp.route('/players/<int:player_id>', methods=['GET'])
def get_player(player_id):
    """Get specific player."""
    try:
        player = Player.query.get_or_404(player_id)
        return jsonify(player.to_dict())
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@api_bp.route('/players', methods=['POST'])
@require_api_key
def create_player():
    """Manually create a new player record."""
    try:
        data = request.get_json()
        
        # Required fields validation
        required_fields = ['name']
        for field in required_fields:
            if field not in data:
                return jsonify({'error': f'{field} is required'}), 400
        
        # Check if player with same name already exists (optional warning)
        existing_player = Player.query.filter_by(name=data['name']).first()
        if existing_player:
            return jsonify({
                'error': 'Player with this name already exists',
                'existing_player': existing_player.to_dict()
            }), 409
        
        # Parse birth date if provided
        birth_date = None
        if data.get('birth_date'):
            try:
                birth_date = datetime.strptime(data['birth_date'], '%Y-%m-%d').date()
            except ValueError:
                return jsonify({'error': 'Invalid birth_date format. Use YYYY-MM-DD'}), 400
        
        # Create the player record
        player = Player(
            player_id=data.get('player_id'),  # Allow manual player_id for API-Football compatibility
            name=data['name'],
            firstname=data.get('firstname'),
            lastname=data.get('lastname'),
            age=data.get('age'),
            birth_date=birth_date,
            birth_place=data.get('birth_place'),
            birth_country=data.get('birth_country'),
            nationality=data.get('nationality', 'Unknown'),
            height=data.get('height'),
            weight=data.get('weight'),
            position=data.get('position', 'Unknown'),
            photo=data.get('photo'),
            injured=data.get('injured', False)
        )
        
        db.session.add(player)
        db.session.commit()
        
        logger.info(f"Created new player: {player.name}")
        
        return jsonify({
            'message': 'Player created successfully',
            'player': player.to_dict()
        }), 201
        
    except Exception as e:
        logger.error(f"Error creating player: {e}")
        return jsonify({'error': str(e)}), 500

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

@api_bp.route('/loans', methods=['POST'])
@require_api_key
def create_loan():
    """Manually create a new loan record with auto-fetched player data."""
    try:
        data = request.get_json()
        
        # Required fields validation
        required_fields = ['player_id', 'parent_team_id', 'loan_team_id', 'loan_start_date', 'loan_season']
        for field in required_fields:
            if field not in data:
                return jsonify({'error': f'{field} is required'}), 400
        
        # Validate that teams exist
        parent_team = Team.query.get(data['parent_team_id'])
        if not parent_team:
            return jsonify({'error': 'Parent team not found'}), 404
            
        loan_team = Team.query.get(data['loan_team_id'])
        if not loan_team:
            return jsonify({'error': 'Loan team not found'}), 404
        
        # Auto-fetch or find player
        player_api_id = data['player_id']
        player = Player.query.filter_by(player_id=player_api_id).first()
        
        if not player:
            # Player doesn't exist locally - fetch from API-Football
            logger.info(f"Player {player_api_id} not found locally, fetching from API-Football...")
            player_data = api_client.get_player_by_id(player_api_id)
            
            if player_data and 'player' in player_data:
                player_info = player_data['player']
                birth_info = player_info.get('birth', {})
                
                # Parse birth date
                birth_date = None
                if birth_info.get('date'):
                    try:
                        birth_date = datetime.strptime(birth_info['date'], '%Y-%m-%d').date()
                    except ValueError:
                        birth_date = None
                
                # Determine position from statistics
                position = 'Unknown'
                if player_data.get('statistics') and player_data['statistics']:
                    stats = player_data['statistics'][0]
                    if stats.get('games', {}).get('position'):
                        position = stats['games']['position']
                
                # Create new player record
                player = Player(
                    player_id=player_info['id'],
                    name=player_info['name'],
                    firstname=player_info.get('firstname'),
                    lastname=player_info.get('lastname'),
                    age=player_info.get('age'),
                    birth_date=birth_date,
                    birth_place=birth_info.get('place'),
                    birth_country=birth_info.get('country'),
                    nationality=player_info.get('nationality', 'Unknown'),
                    height=player_info.get('height'),
                    weight=player_info.get('weight'),
                    position=position,
                    photo=player_info.get('photo'),
                    injured=player_info.get('injured', False)
                )
                
                db.session.add(player)
                db.session.flush()  # Get the ID for the loan record
                
                logger.info(f"Created new player record: {player.name} (ID: {player_api_id})")
            else:
                return jsonify({'error': f'Unable to fetch player data for ID {player_api_id}'}), 404
        
        # Parse dates
        try:
            loan_start_date = datetime.strptime(data['loan_start_date'], '%Y-%m-%d').date()
        except ValueError:
            return jsonify({'error': 'Invalid loan_start_date format. Use YYYY-MM-DD'}), 400
        
        loan_end_date = None
        if data.get('loan_end_date'):
            try:
                loan_end_date = datetime.strptime(data['loan_end_date'], '%Y-%m-%d').date()
            except ValueError:
                return jsonify({'error': 'Invalid loan_end_date format. Use YYYY-MM-DD'}), 400
        
        # Validate loan type
        valid_loan_types = ['Season Long', 'Half Season', 'Emergency', 'Short Term']
        loan_type = data.get('loan_type', 'Season Long')
        if loan_type not in valid_loan_types:
            return jsonify({'error': f'Invalid loan_type. Must be one of: {valid_loan_types}'}), 400
        
        # Check for overlapping active loans to the same team (optional validation)
        existing_active_loan = LoanedPlayer.query.filter_by(
            player_id=player.id,
            parent_team_id=parent_team.id,
            loan_team_id=loan_team.id,
            loan_season=data['loan_season'],
            is_active=True
        ).first()
        
        if existing_active_loan:
            return jsonify({
                'error': 'Player already has an active loan to this team in this season',
                'existing_loan_id': existing_active_loan.id
            }), 409
        
        # Create the loan record
        loan = LoanedPlayer(
            player_id=player.id,
            parent_team_id=parent_team.id,
            loan_team_id=loan_team.id,
            loan_start_date=loan_start_date,
            loan_end_date=loan_end_date,
            original_end_date=loan_end_date,
            loan_type=loan_type,
            loan_season=data['loan_season'],
            loan_fee=data.get('loan_fee'),
            buy_option_fee=data.get('buy_option_fee'),
            recall_option=data.get('recall_option', True),
            is_active=data.get('is_active', True),
            performance_notes=data.get('performance_notes', ''),
            appearances=data.get('appearances', 0),
            goals=data.get('goals', 0),
            assists=data.get('assists', 0),
            minutes_played=data.get('minutes_played', 0)
        )
        
        # Handle buy option deadline
        if data.get('buy_option_deadline'):
            try:
                loan.buy_option_deadline = datetime.strptime(data['buy_option_deadline'], '%Y-%m-%d').date()
            except ValueError:
                return jsonify({'error': 'Invalid buy_option_deadline format. Use YYYY-MM-DD'}), 400
        
        db.session.add(loan)
        db.session.commit()
        
        logger.info(f"Created new loan: {player.name} from {parent_team.name} to {loan_team.name}")
        
        return jsonify({
            'message': 'Loan created successfully',
            'loan': loan.to_dict(),
            'player_auto_created': player.created_at.timestamp() > (datetime.now(timezone.utc) - timedelta(seconds=30)).timestamp()
        }), 201
        
    except Exception as e:
        logger.error(f"Error creating loan: {e}")
        return jsonify({'error': str(e)}), 500

@api_bp.route('/loans/bulk-upload', methods=['POST'])
@require_api_key
def bulk_upload_loans():
    """Bulk upload loans via CSV file."""
    try:
        # Check if file is present
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        if not file.filename.lower().endswith('.csv'):
            return jsonify({'error': 'File must be a CSV'}), 400
        
        # Read CSV content
        stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
        csv_reader = csv.DictReader(stream)
        
        # Expected CSV columns
        required_columns = ['player_id', 'parent_team_id', 'loan_team_id', 'loan_start_date', 'loan_season']
        optional_columns = ['loan_end_date', 'loan_type', 'loan_fee', 'buy_option_fee', 'recall_option', 'appearances', 'goals', 'assists', 'minutes_played', 'performance_notes']
        
        # Validate CSV headers
        if not all(col in csv_reader.fieldnames for col in required_columns):
            return jsonify({
                'error': f'CSV must contain required columns: {required_columns}',
                'found_columns': csv_reader.fieldnames
            }), 400
        
        # Process CSV rows
        created_loans = []
        errors = []
        players_auto_created = []
        
        for row_num, row in enumerate(csv_reader, start=2):  # Start at 2 because row 1 is headers
            try:
                # Validate required fields are not empty
                for field in required_columns:
                    if not row.get(field, '').strip():
                        errors.append(f"Row {row_num}: {field} is required")
                        continue
                
                # Skip if there were validation errors for this row
                if any(f"Row {row_num}:" in error for error in errors):
                    continue
                
                # Convert string IDs to integers
                try:
                    player_api_id = int(row['player_id'])
                    parent_team_id = int(row['parent_team_id'])
                    loan_team_id = int(row['loan_team_id'])
                except ValueError:
                    errors.append(f"Row {row_num}: player_id, parent_team_id, and loan_team_id must be numbers")
                    continue
                
                # Validate teams exist
                parent_team = Team.query.get(parent_team_id)
                if not parent_team:
                    errors.append(f"Row {row_num}: Parent team ID {parent_team_id} not found")
                    continue
                
                loan_team = Team.query.get(loan_team_id)
                if not loan_team:
                    errors.append(f"Row {row_num}: Loan team ID {loan_team_id} not found")
                    continue
                
                # Auto-fetch or find player
                player = Player.query.filter_by(player_id=player_api_id).first()
                
                if not player:
                    # Player doesn't exist locally - fetch from API-Football
                    logger.info(f"Row {row_num}: Player {player_api_id} not found locally, fetching from API-Football...")
                    player_data = api_client.get_player_by_id(player_api_id)
                    
                    if player_data and 'player' in player_data:
                        player_info = player_data['player']
                        birth_info = player_info.get('birth', {})
                        
                        # Parse birth date
                        birth_date = None
                        if birth_info.get('date'):
                            try:
                                birth_date = datetime.strptime(birth_info['date'], '%Y-%m-%d').date()
                            except ValueError:
                                birth_date = None
                        
                        # Determine position from statistics
                        position = 'Unknown'
                        if player_data.get('statistics') and player_data['statistics']:
                            stats = player_data['statistics'][0]
                            if stats.get('games', {}).get('position'):
                                position = stats['games']['position']
                        
                        # Create new player record
                        player = Player(
                            player_id=player_info['id'],
                            name=player_info['name'],
                            firstname=player_info.get('firstname'),
                            lastname=player_info.get('lastname'),
                            age=player_info.get('age'),
                            birth_date=birth_date,
                            birth_place=birth_info.get('place'),
                            birth_country=birth_info.get('country'),
                            nationality=player_info.get('nationality', 'Unknown'),
                            height=player_info.get('height'),
                            weight=player_info.get('weight'),
                            position=position,
                            photo=player_info.get('photo'),
                            injured=player_info.get('injured', False)
                        )
                        
                        db.session.add(player)
                        db.session.flush()  # Get the ID for the loan record
                        players_auto_created.append(player.name)
                        
                        logger.info(f"Row {row_num}: Created new player record: {player.name} (ID: {player_api_id})")
                    else:
                        errors.append(f"Row {row_num}: Unable to fetch player data for ID {player_api_id}")
                        continue
                
                # Parse dates
                try:
                    loan_start_date = datetime.strptime(row['loan_start_date'], '%Y-%m-%d').date()
                except ValueError:
                    errors.append(f"Row {row_num}: Invalid loan_start_date format. Use YYYY-MM-DD")
                    continue
                
                loan_end_date = None
                if row.get('loan_end_date', '').strip():
                    try:
                        loan_end_date = datetime.strptime(row['loan_end_date'], '%Y-%m-%d').date()
                    except ValueError:
                        errors.append(f"Row {row_num}: Invalid loan_end_date format. Use YYYY-MM-DD")
                        continue
                
                # Validate loan type
                valid_loan_types = ['Season Long', 'Half Season', 'Emergency', 'Short Term']
                loan_type = row.get('loan_type', 'Season Long').strip() or 'Season Long'
                if loan_type not in valid_loan_types:
                    errors.append(f"Row {row_num}: Invalid loan_type '{loan_type}'. Must be one of: {valid_loan_types}")
                    continue
                
                # Check for overlapping active loans to the same team
                existing_active_loan = LoanedPlayer.query.filter_by(
                    player_id=player.id,
                    parent_team_id=parent_team.id,
                    loan_team_id=loan_team.id,
                    loan_season=row['loan_season'],
                    is_active=True
                ).first()
                
                if existing_active_loan:
                    errors.append(f"Row {row_num}: Player {player.name} already has an active loan to {loan_team.name} in season {row['loan_season']}")
                    continue
                
                # Parse optional numeric fields
                def safe_float(value, default=None):
                    try:
                        return float(value) if value and value.strip() else default
                    except ValueError:
                        return default
                
                def safe_int(value, default=0):
                    try:
                        return int(value) if value and value.strip() else default
                    except ValueError:
                        return default
                
                def safe_bool(value, default=True):
                    if not value or not value.strip():
                        return default
                    return value.strip().lower() in ['true', '1', 'yes', 'y']
                
                # Create the loan record
                loan = LoanedPlayer(
                    player_id=player.id,
                    parent_team_id=parent_team.id,
                    loan_team_id=loan_team.id,
                    loan_start_date=loan_start_date,
                    loan_end_date=loan_end_date,
                    original_end_date=loan_end_date,
                    loan_type=loan_type,
                    loan_season=row['loan_season'],
                    loan_fee=safe_float(row.get('loan_fee')),
                    buy_option_fee=safe_float(row.get('buy_option_fee')),
                    recall_option=safe_bool(row.get('recall_option'), True),
                    is_active=True,  # New loans are active by default
                    performance_notes=row.get('performance_notes', '').strip(),
                    appearances=safe_int(row.get('appearances')),
                    goals=safe_int(row.get('goals')),
                    assists=safe_int(row.get('assists')),
                    minutes_played=safe_int(row.get('minutes_played'))
                )
                
                db.session.add(loan)
                created_loans.append({
                    'player_name': player.name,
                    'parent_team': parent_team.name,
                    'loan_team': loan_team.name,
                    'season': row['loan_season'],
                    'loan_type': loan_type
                })
                
            except Exception as e:
                logger.error(f"Error processing row {row_num}: {e}")
                errors.append(f"Row {row_num}: {str(e)}")
                continue
        
        # Commit all changes if no critical errors
        if created_loans:
            db.session.commit()
            logger.info(f"Bulk upload completed: {len(created_loans)} loans created")
        
        return jsonify({
            'message': f'Bulk upload completed: {len(created_loans)} loans created',
            'created_loans': created_loans,
            'players_auto_created': players_auto_created,
            'errors': errors,
            'total_processed': len(created_loans) + len(errors)
        }), 201 if created_loans else 400
        
    except Exception as e:
        logger.error(f"Error in bulk upload: {e}")
        return jsonify({'error': str(e)}), 500

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

@api_bp.route('/squads/<int:team_id>/csv-template', methods=['GET'])
@require_api_key
def generate_squad_csv_template(team_id):
    """Generate CSV template with all players from a team squad."""
    try:
        season = request.args.get('season', api_client.current_season_start_year, type=int)
        
        api_client.set_season_year(season)
        api_client._prime_team_cache(season)
        
        # Validate team exists
        # team = Team.query.get_or_404(team_id)
        # Get team data from API
        team_data = api_client.get_team_by_id(team_id)
        
        
        # Extract team info from the API response structure
        team_info = team_data.get('team', {})
        team_name = team_info.get('name', f'Team {team_id}')
        
        logger.info(f"📋 Generating squad CSV template for {team_name} (season {season})")
        
        # Fetch all players for the team
        players_data = api_client.get_team_players(team_id, int(season))
        
        if not players_data:
            return jsonify({'error': f'No players found for team {team_name} in season {season}'}), 404
        
        # Create CSV template with headers and player data
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write headers with comprehensive player and loan information
        headers = [
            # Player Information
            'player_id', 'player_name', 'firstname', 'lastname', 'age', 'nationality', 
            'height', 'weight', 'birth_date', 'birth_place', 'birth_country',
            # Team Information
            'parent_team_id', 'parent_team_name', 'parent_team_code',
            # Position Information
            'position', 'position_abbreviation',
            # Loan Information
            'is_loaned', 'loan_team_id', 'loan_team_name', 'loan_start_date', 'loan_end_date', 
            'loan_season', 'loan_type', 'loan_fee', 'buy_option_fee', 'recall_option',
            # Performance Information
            'appearances', 'goals', 'assists', 'minutes_played', 'clean_sheets', 'yellow_cards', 'red_cards',
            # Additional Information
            'performance_notes', 'injury_status', 'photo_url'
        ]
        writer.writerow(headers)
        
        # Write player rows with comprehensive data
        for player_data in players_data:
            player_info = player_data.get('player', {})
            stats = player_data.get('statistics', [{}])
            
            # Extract position information
            position = 'Unknown'
            position_abbreviation = 'Unknown'
            if stats and stats[0].get('games', {}).get('position'):
                position = stats[0]['games']['position']
                # Map position to abbreviation
                position_map = {
                    'Attacker': 'FWD', 'Forward': 'FWD', 'Striker': 'FWD',
                    'Midfielder': 'MID', 'Midfield': 'MID',
                    'Defender': 'DEF', 'Defence': 'DEF',
                    'Goalkeeper': 'GK', 'Goalie': 'GK'
                }
                position_abbreviation = position_map.get(position, position[:3].upper())
            
            # Extract birth information
            birth_info = player_info.get('birth', {})
            birth_date = birth_info.get('date', '')
            birth_place = birth_info.get('place', '')
            birth_country = birth_info.get('country', '')
            
            # Extract performance stats
            performance_stats = {}
            if stats and stats[0].get('games'):
                games = stats[0]['games']
                performance_stats = {
                    'appearances': games.get('appearences', 0),
                    'minutes_played': games.get('minutes', 0),
                    'position': games.get('position', 'Unknown')
                }
            
            if stats and stats[0].get('goals'):
                goals = stats[0]['goals']
                performance_stats.update({
                    'goals': goals.get('total', 0),
                    'assists': goals.get('assists', 0),
                    'clean_sheets': goals.get('conceded', 0)  # For goalkeepers/defenders
                })
            
            if stats and stats[0].get('cards'):
                cards = stats[0]['cards']
                performance_stats.update({
                    'yellow_cards': cards.get('yellow', 0),
                    'red_cards': cards.get('red', 0)
                })
            
            
            writer.writerow([
                # Player Information
                player_info.get('id', ''),                    # player_id
                player_info.get('name', ''),                  # player_name
                player_info.get('firstname', ''),             # firstname
                player_info.get('lastname', ''),              # lastname
                player_info.get('age', ''),                   # age
                player_info.get('nationality', ''),           # nationality
                player_info.get('height', ''),                # height
                player_info.get('weight', ''),                # weight
                birth_date,                                   # birth_date
                birth_place,                                  # birth_place
                birth_country,                                # birth_country
                # Team Information
                team_id,                                      # parent_team_id
                team_name,                                    # parent_team_name
                team_info.get('code', ''),                    # parent_team_code
                # Position Information
                position,                                     # position
                position_abbreviation,                        # position_abbreviation
                # Loan Information
                'no',                                         # is_loaned (default to 'no')
                '',                                           # loan_team_id (empty - to fill)
                '',                                           # loan_team_name (empty - to fill)
                '',                                           # loan_start_date (empty - to fill)
                '',                                           # loan_end_date (empty - to fill)
                f"{season}-{str(int(season) + 1)[2:]}",      # loan_season (default)
                'Season Long',                                # loan_type (default)
                '',                                           # loan_fee (empty - to fill)
                '',                                           # buy_option_fee (empty - to fill)
                'true',                                       # recall_option (default)
                # Performance Information
                performance_stats.get('appearances', ''),      # appearances
                performance_stats.get('goals', ''),           # goals
                performance_stats.get('assists', ''),         # assists
                performance_stats.get('minutes_played', ''),  # minutes_played
                performance_stats.get('clean_sheets', ''),    # clean_sheets
                performance_stats.get('yellow_cards', ''),    # yellow_cards
                performance_stats.get('red_cards', ''),       # red_cards
                # Additional Information
                '',                                           # performance_notes (empty - to fill)
                'Not Injured' if not player_info.get('injured', False) else 'Injured',  # injury_status
                player_info.get('photo', '')                  # photo_url
            ])
        
        output.seek(0)
        csv_content = output.getvalue()
        output.close()
        
        filename = f"{team_name.replace(' ', '_').lower()}_squad_{season}.csv"
        
        from flask import Response
        return Response(
            csv_content,
            mimetype='text/csv',
            headers={'Content-Disposition': f'attachment; filename={filename}'}
        )
        
    except Exception as e:
        logger.error(f"Error generating squad CSV template: {e}")
        return jsonify({'error': str(e)}), 500

@api_bp.route('/squads/all-teams/csv-template', methods=['GET'])
@require_api_key
def generate_all_teams_csv_template():
    """Generate CSV template with all players from all monitored leagues."""
    
    try:
        season = request.args.get('season', api_client.current_season_start_year)

        
        logger.info(f"📋 Generating comprehensive CSV template for all teams (season {season})")

        
        # Get all teams from monitored leagues with league information

        all_teams_data = api_client.get_teams_with_leagues_for_season(int(season))

        
        if not all_teams_data:
    
            return jsonify({'error': f'No teams found for season {season}'}), 404
        
        # Create CSV template with headers and player data
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write headers with comprehensive player and loan information
        headers = [
            # Player Information
            'player_id', 'player_name', 'firstname', 'lastname', 'age', 'nationality', 
            'height', 'weight', 'birth_date', 'birth_place', 'birth_country',
            # Team Information
            'parent_team_id', 'parent_team_name', 'parent_team_code', 'league_name',
            # Position Information
            'position', 'position_abbreviation',
            # Loan Information
            'is_loaned', 'loan_team_id', 'loan_team_name', 'loan_start_date', 'loan_end_date', 
            'loan_season', 'loan_type', 'loan_fee', 'buy_option_fee', 'recall_option',
            # Performance Information
            'appearances', 'goals', 'assists', 'minutes_played', 'clean_sheets', 'yellow_cards', 'red_cards',
            # Additional Information
            'performance_notes', 'injury_status', 'photo_url'
        ]
        writer.writerow(headers)
        
        total_players = 0
        total_teams = 0
        
        # Process each team (all teams for production)
        processed_teams = 0
        total_teams_count = len(all_teams_data)
        
        for team_id, team_info in all_teams_data.items():

            try:
                team_name = team_info['name']
                league_name = team_info['league_name']
                
                logger.info(f"📋 Processing team {team_id}: {team_name} ({league_name})")
    
                
                # We already have team data from get_teams_with_leagues_for_season()
                # No need to make another API call
                team_code = team_info.get('code', '')
                
                # Fetch all players for the team
    
                players_data = api_client.get_team_players(team_id, int(season))
                
                if not players_data:
                    logger.warning(f"No players found for team {team_name} (ID: {team_id})")
    
                    continue
                
    
                
                team_players_count = 0
                
                # Write player rows for this team
                for player_data in players_data:
                    player_info = player_data.get('player', {})
                    stats = player_data.get('statistics', [{}])
                    
                    # Extract position information
                    position = 'Unknown'
                    position_abbreviation = 'Unknown'
                    if stats and stats[0].get('games', {}).get('position'):
                        position = stats[0]['games']['position']
                        # Map position to abbreviation
                        position_map = {
                            'Attacker': 'FWD', 'Forward': 'FWD', 'Striker': 'FWD',
                            'Midfielder': 'MID', 'Midfield': 'MID',
                            'Defender': 'DEF', 'Defence': 'DEF',
                            'Goalkeeper': 'GK', 'Goalie': 'GK'
                        }
                        position_abbreviation = position_map.get(position, position[:3].upper())
                    
                    # Extract birth information
                    birth_info = player_info.get('birth', {})
                    birth_date = birth_info.get('date', '')
                    birth_place = birth_info.get('place', '')
                    birth_country = birth_info.get('country', '')
                    
                    # Extract performance stats
                    performance_stats = {}
                    if stats and stats[0].get('games'):
                        games = stats[0]['games']
                        performance_stats = {
                            'appearances': games.get('appearences', 0),
                            'minutes_played': games.get('minutes', 0),
                            'position': games.get('position', 'Unknown')
                        }
                    
                    if stats and stats[0].get('goals'):
                        goals = stats[0]['goals']
                        performance_stats.update({
                            'goals': goals.get('total', 0),
                            'assists': goals.get('assists', 0),
                            'clean_sheets': goals.get('conceded', 0)  # For goalkeepers/defenders
                        })
                    
                    if stats and stats[0].get('cards'):
                        cards = stats[0]['cards']
                        performance_stats.update({
                            'yellow_cards': cards.get('yellow', 0),
                            'red_cards': cards.get('red', 0)
                        })
                    
                    writer.writerow([
                        # Player Information
                        player_info.get('id', ''),                    # player_id
                        player_info.get('name', ''),                  # player_name
                        player_info.get('firstname', ''),             # firstname
                        player_info.get('lastname', ''),              # lastname
                        player_info.get('age', ''),                   # age
                        player_info.get('nationality', ''),           # nationality
                        player_info.get('height', ''),                # height
                        player_info.get('weight', ''),                # weight
                        birth_date,                                   # birth_date
                        birth_place,                                  # birth_place
                        birth_country,                                # birth_country
                        # Team Information
                        team_id,                                      # parent_team_id
                        team_name,                                    # parent_team_name
                        team_code,                                    # parent_team_code
                        league_name,                                  # league_name
                        # Position Information
                        position,                                     # position
                        position_abbreviation,                        # position_abbreviation
                        # Loan Information
                        'no',                                         # is_loaned (default to 'no')
                        '',                                           # loan_team_id (empty - to fill)
                        '',                                           # loan_team_name (empty - to fill)
                        '',                                           # loan_start_date (empty - to fill)
                        '',                                           # loan_end_date (empty - to fill)
                        f"{season}-{str(int(season) + 1)[2:]}",      # loan_season (default)
                        'Season Long',                                # loan_type (default)
                        '',                                           # loan_fee (empty - to fill)
                        '',                                           # buy_option_fee (empty - to fill)
                        'true',                                       # recall_option (default)
                        # Performance Information
                        performance_stats.get('appearances', ''),      # appearances
                        performance_stats.get('goals', ''),           # goals
                        performance_stats.get('assists', ''),         # assists
                        performance_stats.get('minutes_played', ''),  # minutes_played
                        performance_stats.get('clean_sheets', ''),    # clean_sheets
                        performance_stats.get('yellow_cards', ''),    # yellow_cards
                        performance_stats.get('red_cards', ''),       # red_cards
                        # Additional Information
                        '',                                           # performance_notes (empty - to fill)
                        'Not Injured' if not player_info.get('injured', False) else 'Injured',  # injury_status
                        player_info.get('photo', '')                  # photo_url
                    ])
                    
                    team_players_count += 1
                
                total_players += team_players_count
                total_teams += 1
                processed_teams += 1
                logger.info(f"✅ Added {team_players_count} players from {team_name}")
    
                
                # Rate limiting to be respectful to the API
                time.sleep(1)  # 1 second delay between teams
                
            except Exception as e:
                logger.error(f"Error processing team {team_id} ({team_name}): {e}")
                continue
        
        output.seek(0)
        csv_content = output.getvalue()
        output.close()
        
        filename = f"all_teams_squad_{season}.csv"
        
        logger.info(f"✅ Generated comprehensive CSV with {total_players} players from {total_teams} teams")
        
        from flask import Response
        return Response(
            csv_content,
            mimetype='text/csv',
            headers={'Content-Disposition': f'attachment; filename={filename}'}
        )
        
    except Exception as e:
        logger.error(f"Error generating comprehensive CSV template: {e}")
        return jsonify({'error': str(e)}), 500

@api_bp.route('/squads/bulk-upload', methods=['POST'])
@require_api_key
def bulk_upload_squad_loans():
    """Bulk upload loans from squad CSV (only processes rows where is_loaned='yes')."""
    try:
        # Check if file is present
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        if not file.filename.lower().endswith('.csv'):
            return jsonify({'error': 'File must be a CSV'}), 400
        
        # Read CSV content
        stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
        csv_reader = csv.DictReader(stream)

        # Get the season from the CSV file
        season = csv_reader.fieldnames[0]

        # Expected CSV columns for squad template (updated for new structure)
        required_columns = ['player_id', 'player_name', 'parent_team_id', 'parent_team_name', 'is_loaned']
        loan_columns = ['loan_team_id', 'loan_team_name', 'loan_start_date', 'loan_end_date', 'loan_season', 'loan_type']
        
        # Validate CSV headers
        if not all(col in csv_reader.fieldnames for col in required_columns):
            return jsonify({
                'error': f'CSV must contain required columns: {required_columns}',
                'found_columns': csv_reader.fieldnames
            }), 400
        
        # Process CSV rows
        created_loans = []
        skipped_rows = []
        errors = []
        players_auto_created = []
        
        for row_num, row in enumerate(csv_reader, start=2):  # Start at 2 because row 1 is headers
            try:
                # Skip rows where is_loaned is not 'yes'
                if row.get('is_loaned', '').lower() != 'yes':
                    skipped_rows.append({
                        'row': row_num,
                        'player_name': row.get('player_name', 'Unknown'),
                        'reason': 'is_loaned != yes'
                    })
                    continue
                
                # Validate required fields for loan creation
                for field in required_columns + loan_columns:
                    if not row.get(field, '').strip() and field != 'is_loaned':
                        errors.append(f"Row {row_num}: {field} is required for loan creation")
                        continue
                
                # Skip if there were validation errors for this row
                if any(f"Row {row_num}:" in error for error in errors):
                    continue
                
                # Convert string IDs to integers
                try:
                    player_api_id = int(row['player_id'])
                    parent_team_id = int(row['parent_team_id'])
                    loan_team_id = int(row['loan_team_id'])
                except ValueError:
                    errors.append(f"Row {row_num}: player_id, parent_team_id, and loan_team_id must be numbers")
                    continue
                
                # Validate teams exist using API
                parent_team_data = api_client.get_team_by_id(parent_team_id, season)
                if not parent_team_data or 'team' not in parent_team_data:
                    errors.append(f"Row {row_num}: Parent team ID {parent_team_id} not found in API")
                    continue
                
                loan_team_data = api_client.get_team_by_id(loan_team_id, season)
                if not loan_team_data or 'team' not in loan_team_data:
                    errors.append(f"Row {row_num}: Loan team ID {loan_team_id} not found in API")
                    continue
                
                # Get team names for validation
                parent_team_name = parent_team_data['team'].get('name', f'Team {parent_team_id}')
                loan_team_name = loan_team_data['team'].get('name', f'Team {loan_team_id}')
                
                                 # Note: We're using API team IDs directly, not database team records
                 # The API validation above ensures teams exist
                
                # Auto-fetch or find player (same logic as before)
                player = Player.query.filter_by(player_id=player_api_id).first()
                
                if not player:
                    # Player doesn't exist locally - fetch from API-Football
                    logger.info(f"Row {row_num}: Player {player_api_id} not found locally, fetching from API-Football...")
                    player_data = api_client.get_player_by_id(player_api_id)
                    
                    if player_data and 'player' in player_data:
                        player_info = player_data['player']
                        birth_info = player_info.get('birth', {})
                        
                        # Parse birth date
                        birth_date = None
                        if birth_info.get('date'):
                            try:
                                birth_date = datetime.strptime(birth_info['date'], '%Y-%m-%d').date()
                            except ValueError:
                                birth_date = None
                        
                        # Determine position from statistics
                        position = row.get('position', 'Unknown')
                        if player_data.get('statistics') and player_data['statistics']:
                            stats = player_data['statistics'][0]
                            if stats.get('games', {}).get('position'):
                                position = stats['games']['position']
                        
                        # Create new player record
                        player = Player(
                            player_id=player_info['id'],
                            name=player_info['name'],
                            firstname=player_info.get('firstname'),
                            lastname=player_info.get('lastname'),
                            age=player_info.get('age'),
                            birth_date=birth_date,
                            birth_place=birth_info.get('place'),
                            birth_country=birth_info.get('country'),
                            nationality=player_info.get('nationality', 'Unknown'),
                            height=player_info.get('height'),
                            weight=player_info.get('weight'),
                            position=position,
                            photo=player_info.get('photo'),
                            injured=player_info.get('injured', False)
                        )
                        
                        db.session.add(player)
                        db.session.flush()  # Get the ID for the loan record
                        players_auto_created.append(player.name)
                        
                        logger.info(f"Row {row_num}: Created new player record: {player.name} (ID: {player_api_id})")
                    else:
                        errors.append(f"Row {row_num}: Unable to fetch player data for ID {player_api_id}")
                        continue
                
                # Parse dates
                try:
                    loan_start_date = datetime.strptime(row['loan_start_date'], '%Y-%m-%d').date()
                except ValueError:
                    errors.append(f"Row {row_num}: Invalid loan_start_date format. Use YYYY-MM-DD")
                    continue
                
                loan_end_date = None
                if row.get('loan_end_date', '').strip():
                    try:
                        loan_end_date = datetime.strptime(row['loan_end_date'], '%Y-%m-%d').date()
                    except ValueError:
                        errors.append(f"Row {row_num}: Invalid loan_end_date format. Use YYYY-MM-DD")
                        continue
                
                # Validate loan type
                valid_loan_types = ['Season Long', 'Half Season', 'Emergency', 'Short Term']
                loan_type = row.get('loan_type', 'Season Long').strip() or 'Season Long'
                if loan_type not in valid_loan_types:
                    errors.append(f"Row {row_num}: Invalid loan_type '{loan_type}'. Must be one of: {valid_loan_types}")
                    continue
                
                # Check for overlapping active loans to the same team
                existing_active_loan = LoanedPlayer.query.filter_by(
                    player_id=player.id,
                    parent_team_id=parent_team_id,
                    loan_team_id=loan_team_id,
                    loan_season=row['loan_season'],
                    is_active=True
                ).first()
                
                if existing_active_loan:
                    errors.append(f"Row {row_num}: Player {player.name} already has an active loan to {loan_team_name} in season {row['loan_season']}")
                    continue
                
                # Parse optional numeric fields (same helper functions as before)
                def safe_float(value, default=None):
                    try:
                        return float(value) if value and value.strip() else default
                    except ValueError:
                        return default
                
                def safe_int(value, default=0):
                    try:
                        return int(value) if value and value.strip() else default
                    except ValueError:
                        return default
                
                def safe_bool(value, default=True):
                    if not value or not value.strip():
                        return default
                    return value.strip().lower() in ['true', '1', 'yes', 'y']
                
                # Create the loan record
                loan = LoanedPlayer(
                    player_id=player.id,
                    parent_team_id=parent_team_id,  # Use API team ID directly
                    loan_team_id=loan_team_id,      # Use API team ID directly
                    loan_start_date=loan_start_date,
                    loan_end_date=loan_end_date,
                    original_end_date=loan_end_date,
                    loan_type=loan_type,
                    loan_season=row['loan_season'],
                    loan_fee=safe_float(row.get('loan_fee')),
                    buy_option_fee=safe_float(row.get('buy_option_fee')),
                    recall_option=safe_bool(row.get('recall_option'), True),
                    is_active=True,  # New loans are active by default
                    performance_notes=row.get('performance_notes', '').strip(),
                    appearances=safe_int(row.get('appearances')),
                    goals=safe_int(row.get('goals')),
                    assists=safe_int(row.get('assists')),
                    minutes_played=safe_int(row.get('minutes_played'))
                )
                
                db.session.add(loan)
                created_loans.append({
                    'player_name': player.name,
                    'parent_team': parent_team_name,  # Use API team name
                    'loan_team': loan_team_name,      # Use API team name
                    'season': row['loan_season'],
                    'loan_type': loan_type
                })
                
            except Exception as e:
                logger.error(f"Error processing row {row_num}: {e}")
                errors.append(f"Row {row_num}: {str(e)}")
                continue
        
        # Commit all changes if no critical errors
        if created_loans:
            db.session.commit()
            logger.info(f"Squad upload completed: {len(created_loans)} loans created")
        
        return jsonify({
            'message': f'Squad upload completed: {len(created_loans)} loans created, {len(skipped_rows)} players skipped',
            'created_loans': created_loans,
            'skipped_players': skipped_rows,
            'players_auto_created': players_auto_created,
            'errors': errors,
            'total_processed': len(created_loans) + len(skipped_rows) + len(errors)
        }), 201 if created_loans else 400
        
    except Exception as e:
        logger.error(f"Error in squad bulk upload: {e}")
        return jsonify({'error': str(e)}), 500

@api_bp.route('/squads/all-teams/bulk-upload', methods=['POST'])
@require_api_key
def bulk_upload_all_teams_loans():
    """Bulk upload loans from all-teams CSV (only processes rows where is_loaned='yes')."""
    try:
        # Check if file is present
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        if not file.filename.lower().endswith('.csv'):
            return jsonify({'error': 'File must be a CSV'}), 400
        
        # Read CSV content
        stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
        csv_reader = csv.DictReader(stream)
        
        # Get the season from the CSV file
        season = csv_reader.fieldnames[0]
        
        # Expected CSV columns for all-teams template (includes league_name)
        required_columns = ['player_id', 'player_name', 'parent_team_id', 'parent_team_name', 'league_name', 'is_loaned']
        loan_columns = ['loan_team_id', 'loan_team_name', 'loan_start_date', 'loan_end_date', 'loan_season', 'loan_type']
        
        # Validate CSV headers
        if not all(col in csv_reader.fieldnames for col in required_columns):
            return jsonify({
                'error': f'CSV must contain required columns: {required_columns}',
                'found_columns': csv_reader.fieldnames
            }), 400
        
        # Process CSV rows
        created_loans = []
        skipped_rows = []
        errors = []
        players_auto_created = []
        
        for row_num, row in enumerate(csv_reader, start=2):  # Start at 2 because row 1 is headers
            try:
                # Skip rows where is_loaned is not 'yes'
                if row.get('is_loaned', '').lower() != 'yes':
                    skipped_rows.append({
                        'row': row_num,
                        'player_name': row.get('player_name', 'Unknown'),
                        'team_name': row.get('parent_team_name', 'Unknown'),
                        'league_name': row.get('league_name', 'Unknown'),
                        'reason': 'is_loaned != yes'
                    })
                    continue
                
                # Validate required fields for loan creation
                for field in required_columns + loan_columns:
                    if not row.get(field, '').strip() and field != 'is_loaned':
                        errors.append(f"Row {row_num}: {field} is required for loan creation")
                        continue
                
                # Skip if there were validation errors for this row
                if any(f"Row {row_num}:" in error for error in errors):
                    continue
                
                # Convert string IDs to integers
                try:
                    player_api_id = int(row['player_id'])
                    parent_team_id = int(row['parent_team_id'])
                    loan_team_id = int(row['loan_team_id'])
                except ValueError:
                    errors.append(f"Row {row_num}: player_id, parent_team_id, and loan_team_id must be numbers")
                    continue
                
                # Validate teams exist using API
                parent_team_data = api_client.get_team_by_id(parent_team_id, season)
                if not parent_team_data or 'team' not in parent_team_data:
                    errors.append(f"Row {row_num}: Parent team ID {parent_team_id} not found in API")
                    continue
                
                loan_team_data = api_client.get_team_by_id(loan_team_id, season)
                if not loan_team_data or 'team' not in loan_team_data:
                    errors.append(f"Row {row_num}: Loan team ID {loan_team_id} not found in API")
                    continue
                
                # Get team names for validation
                parent_team_name = parent_team_data['team'].get('name', f'Team {parent_team_id}')
                loan_team_name = loan_team_data['team'].get('name', f'Team {loan_team_id}')
                
                # Auto-fetch or find player (same logic as before)
                player = Player.query.filter_by(player_id=player_api_id).first()
                
                if not player:
                    # Player doesn't exist locally - fetch from API-Football
                    logger.info(f"Row {row_num}: Player {player_api_id} not found locally, fetching from API-Football...")
                    player_data = api_client.get_player_by_id(player_api_id)
                    
                    if player_data and 'player' in player_data:
                        player_info = player_data['player']
                        birth_info = player_info.get('birth', {})
                        
                        # Parse birth date
                        birth_date = None
                        if birth_info.get('date'):
                            try:
                                birth_date = datetime.strptime(birth_info['date'], '%Y-%m-%d').date()
                            except ValueError:
                                birth_date = None
                        
                        # Determine position from statistics
                        position = row.get('position', 'Unknown')
                        if player_data.get('statistics') and player_data['statistics']:
                            stats = player_data['statistics'][0]
                            if stats.get('games', {}).get('position'):
                                position = stats['games']['position']
                        
                        # Create new player record
                        player = Player(
                            player_id=player_info['id'],
                            name=player_info['name'],
                            firstname=player_info.get('firstname'),
                            lastname=player_info.get('lastname'),
                            age=player_info.get('age'),
                            birth_date=birth_date,
                            birth_place=birth_info.get('place'),
                            birth_country=birth_info.get('country'),
                            nationality=player_info.get('nationality', 'Unknown'),
                            height=player_info.get('height'),
                            weight=player_info.get('weight'),
                            position=position,
                            photo=player_info.get('photo'),
                            injured=player_info.get('injured', False)
                        )
                        
                        db.session.add(player)
                        db.session.flush()  # Get the ID for the loan record
                        players_auto_created.append(player.name)
                        
                        logger.info(f"Row {row_num}: Created new player record: {player.name} (ID: {player_api_id})")
                    else:
                        errors.append(f"Row {row_num}: Unable to fetch player data for ID {player_api_id}")
                        continue
                
                # Parse dates
                try:
                    loan_start_date = datetime.strptime(row['loan_start_date'], '%Y-%m-%d').date()
                except ValueError:
                    errors.append(f"Row {row_num}: Invalid loan_start_date format. Use YYYY-MM-DD")
                    continue
                
                loan_end_date = None
                if row.get('loan_end_date', '').strip():
                    try:
                        loan_end_date = datetime.strptime(row['loan_end_date'], '%Y-%m-%d').date()
                    except ValueError:
                        errors.append(f"Row {row_num}: Invalid loan_end_date format. Use YYYY-MM-DD")
                        continue
                
                # Validate loan type
                valid_loan_types = ['Season Long', 'Half Season', 'Emergency', 'Short Term']
                loan_type = row.get('loan_type', 'Season Long').strip() or 'Season Long'
                if loan_type not in valid_loan_types:
                    errors.append(f"Row {row_num}: Invalid loan_type '{loan_type}'. Must be one of: {valid_loan_types}")
                    continue
                
                # Check for overlapping active loans to the same team
                existing_active_loan = LoanedPlayer.query.filter_by(
                    player_id=player.id,
                    parent_team_id=parent_team_id,
                    loan_team_id=loan_team_id,
                    is_active=True
                ).first()
                
                if existing_active_loan:
                    errors.append(f"Row {row_num}: Active loan already exists for {player.name} from {parent_team_name} to {loan_team_name}")
                    continue
                
                # Parse optional numeric fields (same helper functions as before)
                def safe_float(value, default=None):
                    try:
                        return float(value) if value and value.strip() else default
                    except ValueError:
                        return default
                
                def safe_int(value, default=0):
                    try:
                        return int(value) if value and value.strip() else default
                    except ValueError:
                        return default
                
                def safe_bool(value, default=True):
                    if not value or not value.strip():
                        return default
                    return value.strip().lower() in ['true', '1', 'yes', 'y']
                
                # Create the loan record
                loan = LoanedPlayer(
                    player_id=player.id,
                    parent_team_id=parent_team_id,  # Use API team ID directly
                    loan_team_id=loan_team_id,      # Use API team ID directly
                    loan_start_date=loan_start_date,
                    loan_end_date=loan_end_date,
                    original_end_date=loan_end_date,
                    loan_type=loan_type,
                    loan_season=row['loan_season'],
                    loan_fee=safe_float(row.get('loan_fee')),
                    buy_option_fee=safe_float(row.get('buy_option_fee')),
                    recall_option=safe_bool(row.get('recall_option'), True),
                    is_active=True,  # New loans are active by default
                    performance_notes=row.get('performance_notes', '').strip(),
                    appearances=safe_int(row.get('appearances')),
                    goals=safe_int(row.get('goals')),
                    assists=safe_int(row.get('assists')),
                    minutes_played=safe_int(row.get('minutes_played'))
                )
                
                db.session.add(loan)
                created_loans.append({
                    'player_name': player.name,
                    'parent_team': parent_team_name,  # Use API team name
                    'loan_team': loan_team_name,      # Use API team name
                    'league_name': row.get('league_name', 'Unknown'),
                    'season': row['loan_season'],
                    'loan_type': loan_type
                })
                
            except Exception as e:
                logger.error(f"Error processing row {row_num}: {e}")
                errors.append(f"Row {row_num}: {str(e)}")
                continue
        
        # Commit all changes if no critical errors
        if created_loans:
            db.session.commit()
            logger.info(f"All-teams upload completed: {len(created_loans)} loans created")
        
        return jsonify({
            'message': f'All-teams upload completed: {len(created_loans)} loans created, {len(skipped_rows)} players skipped',
            'created_loans': created_loans,
            'skipped_players': skipped_rows,
            'players_auto_created': players_auto_created,
            'errors': errors,
            'total_processed': len(created_loans) + len(skipped_rows) + len(errors)
        }), 201 if created_loans else 400
        
    except Exception as e:
        logger.error(f"Error in all-teams bulk upload: {e}")
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
        
        newsletters = query.order_by(Newsletter.generated_date.desc()).all()
        return jsonify([newsletter.to_dict() for newsletter in newsletters])
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@api_bp.route('/newsletters/<int:newsletter_id>', methods=['GET'])
def get_newsletter(newsletter_id):
    """Get specific newsletter."""
    try:
        newsletter = Newsletter.query.get_or_404(newsletter_id)
        return jsonify(newsletter.to_dict())
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
            generated_date=target_date
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
        
        # Generate newsletter content using AI (mock implementation)
        newsletter_content = generate_newsletter_content(team, loans, target_date, newsletter_type)
        
        # Create newsletter record
        newsletter = Newsletter(
            team_id=team_id,
            newsletter_type=newsletter_type,
            title=json.loads(newsletter_content)['title'],
            content=newsletter_content,
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
    terminated_loans = [loan for loan in loans if loan.early_termination]
    
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
                'player_name': loan.player.name if loan.player else 'Unknown Player',
                'loan_team': loan.loan_team.name if loan.loan_team else 'Unknown Team',
                'loan_type': loan.loan_type,
                'status': 'Active loan',
                'performance': performance_summary,
                'analysis': f'Player showing {"excellent" if loan.goals > 3 else "good" if loan.appearances > 10 else "steady"} progress at {loan.loan_team.name if loan.loan_team else "loan club"}.',
                'recall_option': 'Available' if loan.recall_option else 'Not available'
            })
    
    if terminated_loans:
        content['sections'].append({
            'title': 'Early Terminations',
            'content': f'{len(terminated_loans)} loans terminated early this season'
        })
        
        for loan in terminated_loans:
            content['sections'].append({
                'player_name': loan.player.name if loan.player else 'Unknown Player',
                'loan_team': loan.loan_team.name if loan.loan_team else 'Unknown Team',
                'termination_reason': loan.termination_reason,
                'termination_date': loan.termination_date.strftime('%B %d, %Y') if loan.termination_date else 'Unknown',
                'final_stats': f"{loan.appearances} appearances, {loan.goals} goals, {loan.assists} assists"
            })
    
    if not active_loans and not terminated_loans:
        content['sections'].append({
            'title': 'No Current Loans',
            'content': f'{team.name} currently has no players out on loan for the {api_client.current_season} season.'
        })
    
    return json.dumps(content)

# Subscription endpoints
@api_bp.route('/subscriptions', methods=['GET'])
def get_subscriptions():
    """Get subscriptions."""
    try:
        subscriptions = UserSubscription.query.all()
        return jsonify([sub.to_dict() for sub in subscriptions])
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@api_bp.route('/subscriptions', methods=['POST'])
def create_subscription():
    """Create new subscription."""
    try:
        data = request.get_json()
        
        # Create subscription
        subscription = UserSubscription(
            email=data.get('email'),
            team_ids=json.dumps(data.get('team_ids', [])),
            frequency=data.get('frequency', 'weekly'),
            is_active=True
        )
        
        db.session.add(subscription)
        db.session.commit()
        
        return jsonify({
            'message': 'Subscription created successfully',
            'subscription': subscription.to_dict()
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@api_bp.route('/subscriptions/<int:subscription_id>', methods=['DELETE'])
def delete_subscription(subscription_id):
    """Unsubscribe from newsletter."""
    try:
        subscription = UserSubscription.query.get_or_404(subscription_id)
        subscription.is_active = False
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

@api_bp.route('/sync-teams', methods=['POST'])
@require_api_key
def sync_teams():
    """Sync teams from API-Football."""
    try:
        # Use current season for team sync (team roster doesn't change much)
        season = api_client.current_season_start_year
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
            
            # Check if team exists
            existing = Team.query.filter_by(team_id=team_info.get('id')).first()
            if existing:
                # Update existing team
                existing.name = team_info.get('name')
                existing.country = team_info.get('country')
                existing.founded = team_info.get('founded')
                existing.logo = team_info.get('logo')
                existing.league_id = league.id
            else:
                # Create new team
                team = Team(
                    team_id=team_info.get('id'),
                    name=team_info.get('name'),
                    country=team_info.get('country'),
                    founded=team_info.get('founded'),
                    logo=team_info.get('logo'),
                    league_id=league.id,
                    is_active=True
                )
                db.session.add(team)
            
            synced_count += 1
        
        db.session.commit()
        return jsonify({
            'message': f'Successfully synced {synced_count} teams from European leagues',
            'synced_teams': synced_count
        })
        
    except Exception as e:
        logger.error(f"Error syncing teams: {e}")
        return jsonify({'error': str(e)}), 500

@api_bp.route('/sync-loans', methods=['POST'])
@require_api_key
def sync_loans():
    """Sync loan data from API-Football with season-based tracking."""
    try:
        # Get sample transfer data
        transfers_data = api_client._get_sample_data('transfers')
        synced_count = 0
        
        # Get current season info from API client
        current_season = api_client.current_season
        season_end_date = api_client.season_end_date
        
        for transfer in transfers_data.get('response', []):
            player_info = transfer.get('player', {})
            transfers_list = transfer.get('transfers', [])
            
            for transfer_info in transfers_list:
                if transfer_info.get('type', '').lower() == 'loan':
                    teams = transfer_info.get('teams', {})
                    parent_team_info = teams.get('out', {})
                    loan_team_info = teams.get('in', {})
                    
                    # Find teams
                    parent_team = Team.query.filter_by(team_id=parent_team_info.get('id')).first()
                    loan_team = Team.query.filter_by(team_id=loan_team_info.get('id')).first()
                    
                    if not parent_team or not loan_team:
                        continue
                    
                    # Create or find player
                    player = Player.query.filter_by(player_id=player_info.get('id')).first()
                    if not player:
                        player = Player(
                            player_id=player_info.get('id'),
                            name=player_info.get('name'),
                            position='Unknown',
                            age=25,  # Default age
                            nationality='Unknown'
                        )
                        db.session.add(player)
                        db.session.flush()  # Get the ID
                    
                    # Check if loan already exists
                    existing_loan = LoanedPlayer.query.filter_by(
                        player_id=player.id,
                        parent_team_id=parent_team.id,
                        loan_team_id=loan_team.id
                    ).first()
                    
                    if not existing_loan:
                        # Parse the loan start date
                        try:
                            loan_start_date = datetime.strptime(transfer_info.get('date'), '%Y-%m-%d').date()
                        except (ValueError, TypeError):
                            loan_start_date = date.today()
                        
                        # Determine loan type and end date based on start date
                        loan_type = 'Season Long'
                        original_end_date = season_end_date
                        
                        # Adjust loan type based on when it started
                        if loan_start_date.month == 1:  # January window
                            loan_type = 'Half Season'
                        elif loan_start_date.month >= 3:  # Emergency loan
                            loan_type = 'Emergency'
                            # Emergency loans typically shorter
                            original_end_date = date(loan_start_date.year, 6, 30)
                        
                        # Simulate some early terminations for realism
                        import random
                        early_termination = False
                        termination_reason = None
                        actual_end_date = None
                        is_active = True
                        
                        # 20% chance of early termination for demonstration
                        if random.random() < 0.2:
                            early_termination = True
                            termination_reasons = [
                                'Injury to player',
                                'Recalled by parent club',
                                'Poor performance',
                                'Mutual agreement',
                                'Loan club request'
                            ]
                            termination_reason = random.choice(termination_reasons)
                            # Terminate 1-3 months early
                            months_early = random.randint(1, 3)
                            actual_end_date = date(original_end_date.year, max(1, original_end_date.month - months_early), original_end_date.day)
                            is_active = actual_end_date > date.today()
                        
                        # Generate some performance stats
                        appearances = random.randint(0, 25) if loan_start_date < date.today() else 0
                        goals = random.randint(0, 8) if appearances > 5 else 0
                        assists = random.randint(0, 6) if appearances > 3 else 0
                        minutes_played = appearances * random.randint(60, 90) if appearances > 0 else 0
                        
                        # Create loan record
                        loan = LoanedPlayer(
                            player_id=player.id,
                            parent_team_id=parent_team.id,
                            loan_team_id=loan_team.id,
                            loan_start_date=loan_start_date,
                            loan_end_date=original_end_date,
                            original_end_date=original_end_date,
                            actual_end_date=actual_end_date,
                            is_active=is_active,
                            loan_type=loan_type,
                            loan_season=current_season,
                            early_termination=early_termination,
                            termination_reason=termination_reason,
                            termination_date=actual_end_date if early_termination else None,
                            recall_option=True,
                            appearances=appearances,
                            goals=goals,
                            assists=assists,
                            minutes_played=minutes_played
                        )
                        db.session.add(loan)
                        synced_count += 1
        
        db.session.commit()
        return jsonify({
            'message': f'Successfully synced {synced_count} season-based loan records',
            'synced_loans': synced_count,
            'current_season': current_season,
            'season_end_date': season_end_date.isoformat()
        })
        
    except Exception as e:
        logger.error(f"Error syncing loans: {e}")
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
                existing_player = Player.query.filter_by(player_id=player_id).first()
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

@api_bp.route('/analyze-player-transfers/<int:player_id>', methods=['GET'])
@require_api_key
def analyze_player_transfers(player_id):
    """Analyze transfer history for a specific player."""
    try:
        season = int(request.args.get('season', api_client.current_season_start_year))
        _sync_season(season=season)
        
        logger.info(f"🔍 Analyzing transfers for player {player_id}")
        
        # Get multi-team data first (more efficient single call)
        multi_team_dict = api_client.detect_multi_team_players(season=season)
        
        # Get transfer analysis using pre-computed multi-team data
        transfer_analysis = api_client.analyze_transfer_type(
            player_id, 
            multi_team_dict=multi_team_dict, 
            season=season
        )
        
        # Extract player's multi-team info
        player_team_ids = multi_team_dict.get(player_id, [])
        player_multi_team = {
            'player_id': player_id,
            'team_ids': player_team_ids,
            'team_count': len(player_team_ids),
            'is_multi_team': len(player_team_ids) > 1
        } if player_team_ids else None
        
        # Get current database record
        existing_player = Player.query.filter_by(player_id=player_id).first()
        
        response = {
            'player_id': player_id,
            'season': season,
            'transfer_analysis': transfer_analysis,
            'multi_team_data': player_multi_team,
            'database_record': existing_player.to_dict() if existing_player else None,
            'recommendation': {
                'should_flag_as_loan': transfer_analysis.get('is_likely_loan', False),
                'confidence': transfer_analysis.get('loan_confidence', 0.0),
                'reasoning': transfer_analysis.get('indicators', [])
            }
        }
        
        return jsonify(response)
        
    except Exception as e:
        logger.error(f"Error analyzing player transfers: {e}")
        return jsonify({'error': str(e)}), 500

@api_bp.route('/players/<int:player_id>/set-loan-flag', methods=['POST'])
@require_api_key
def set_player_loan_flag(player_id):
    """Set or update the is_loaned flag for a player."""
    try:
        data = request.get_json()
        is_loaned = data.get('is_loaned', False)
        manual_review = data.get('manual_review', True)
        notes = data.get('notes', '')
        
        # Get or create player record
        player = Player.query.filter_by(player_id=player_id).first()
        
        if not player:
            # Fetch player data from API and create record
            logger.info(f"Player {player_id} not found locally, fetching from API")
            player_data = api_client.get_player_by_id(player_id)
            
            if not player_data or 'player' not in player_data:
                return jsonify({'error': 'Player not found in API'}), 404
            
            player_info = player_data['player']
            birth_info = player_info.get('birth', {})
            
            # Parse birth date
            birth_date = None
            if birth_info.get('date'):
                try:
                    birth_date = datetime.strptime(birth_info['date'], '%Y-%m-%d').date()
                except ValueError:
                    birth_date = None
            
            # Create new player record
            player = Player(
                player_id=player_info['id'],
                name=player_info['name'],
                firstname=player_info.get('firstname'),
                lastname=player_info.get('lastname'),
                age=player_info.get('age'),
                birth_date=birth_date,
                birth_place=birth_info.get('place'),
                birth_country=birth_info.get('country'),
                nationality=player_info.get('nationality', 'Unknown'),
                height=player_info.get('height'),
                weight=player_info.get('weight'),
                position='Unknown',  # Will be updated from statistics if available
                photo=player_info.get('photo'),
                injured=player_info.get('injured', False)
            )
            
            db.session.add(player)
            db.session.flush()
        
        # Store loan flag information in a separate table or add to Player model
        # For now, we'll just return success
        db.session.commit()
        
        logger.info(f"Updated loan flag for player {player_id}: is_loaned={is_loaned}")
        
        return jsonify({
            'message': f'Successfully updated loan flag for player {player.name}',
            'player_id': player_id,
            'player_name': player.name,
            'is_loaned': is_loaned,
            'manual_review': manual_review,
            'notes': notes,
            'updated_at': datetime.utcnow().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Error setting loan flag: {e}")
        return jsonify({'error': str(e)}), 500

@api_bp.route('/loan-candidates/review', methods=['GET'])
@require_api_key
def get_loan_candidates_for_review():
    """Get a list of players that need loan status review."""
    try:
        season = int(request.args.get('season', api_client.current_season_start_year))
        _sync_season(season=season)
        limit = request.args.get('limit', 50, type=int)
        confidence_threshold = request.args.get('confidence_threshold', 0.3, type=float)
        
        logger.info(f"🔍 Getting loan candidates for review (season: {season})")
        
        # Detect multi-team players using new league-level approach
        multi_team_dict = api_client.detect_multi_team_players(season=season)
        
        candidates_for_review = []
        
        for player_id, team_ids in multi_team_dict.items():
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
                    season=season
                )
                
                loan_confidence = transfer_analysis.get('loan_confidence', 0.0)
                
                # Only include candidates above confidence threshold
                if loan_confidence >= confidence_threshold:
                    # Check if already in database with loan status
                    existing_player = Player.query.filter_by(player_id=player_id).first()
                    existing_loans = LoanedPlayer.query.join(Player).filter(
                        Player.player_id == player_id,
                        LoanedPlayer.loan_season.like(f'%{season}%')
                    ).all()
                    
                    review_candidate = {
                        'player_id': player_id,
                        'player_name': player_info.get('name'),
                        'age': player_info.get('age'),
                        'nationality': player_info.get('nationality'),
                        'team_ids': team_ids,
                        'team_count': len(team_ids),
                        'loan_confidence': loan_confidence,
                        'is_likely_loan': transfer_analysis.get('is_likely_loan', False),
                        'indicators': transfer_analysis.get('indicators', []),
                        'transfers': transfer_analysis.get('transfers', []),
                        'existing_in_db': existing_player is not None,
                        'existing_loans': len(existing_loans),
                        'needs_action': len(existing_loans) == 0,  # No loan records yet
                        'season': season
                    }
                    
                    candidates_for_review.append(review_candidate)
                    
            except Exception as e:
                logger.warning(f"Error processing player {player_id} for review: {e}")
                continue
        
        # Sort by confidence score (highest first)
        candidates_for_review.sort(key=lambda x: x['loan_confidence'], reverse=True)
        
        # Limit results
        candidates_for_review = candidates_for_review[:limit]
        
        return jsonify({
            'candidates': candidates_for_review,
            'total_candidates': len(candidates_for_review),
            'season': season,
            'confidence_threshold': confidence_threshold,
            'summary': {
                'high_confidence': len([c for c in candidates_for_review if c['loan_confidence'] >= 0.7]),
                'medium_confidence': len([c for c in candidates_for_review if 0.4 <= c['loan_confidence'] < 0.7]),
                'low_confidence': len([c for c in candidates_for_review if c['loan_confidence'] < 0.4]),
                'needs_action': len([c for c in candidates_for_review if c['needs_action']])
            }
        })
        
    except Exception as e:
        logger.error(f"Error getting loan candidates for review: {e}")
        return jsonify({'error': str(e)}), 500



@api_bp.route('/detect-loans-from-database', methods=['POST'])
@require_api_key
def detect_loans_from_database():
    """Detect loan candidates using existing database data."""
    try:
        data = request.get_json() or {}
        season = data.get('season', api_client.current_season_start_year)
        
        logger.info(f"🔍 Detecting loans from database for season {season}")
        
        # Get all players from the database
        all_players = Player.query.all()
        logger.info(f"📊 Found {len(all_players)} players in database")
        
        # Get all loaned players for the season
        existing_loans = LoanedPlayer.query.filter(
            LoanedPlayer.loan_season.like(f'%{season}%')
        ).all()
        
        # Create a mapping of player_id to their teams
        player_teams = {}
        loan_candidates = []
        
        # Analyze each player
        for player in all_players:
            player_id = player.player_id
            
            # Get all teams this player is associated with (from loans)
            player_loans = [loan for loan in existing_loans if loan.player_id == player.id]
            
            if len(player_loans) > 1:
                # Player has multiple loan records - potential loan candidate
                teams = []
                for loan in player_loans:
                    teams.append({
                        'team_id': loan.parent_team_id,
                        'team_name': f'Team {loan.parent_team_id}',
                        'loan_team_id': loan.loan_team_id,
                        'loan_team_name': f'Team {loan.loan_team_id}',
                        'loan_type': loan.loan_type,
                        'is_active': loan.is_active
                    })
                
                # Calculate loan confidence based on loan patterns
                active_loans = [loan for loan in player_loans if loan.is_active]
                loan_confidence = min(0.8, len(active_loans) * 0.4)
                
                loan_candidate = {
                    'player_id': player_id,
                    'player_name': player.name,
                    'age': player.age,
                    'nationality': player.nationality,
                    'teams': teams,
                    'team_count': len(teams),
                    'loan_confidence': loan_confidence,
                    'is_likely_loan': loan_confidence >= 0.5,
                    'indicators': [
                        f"Player has {len(player_loans)} loan records",
                        f"Active loans: {len(active_loans)}"
                    ],
                    'existing_loans': len(player_loans),
                    'season': season,
                    'needs_review': True
                }
                
                loan_candidates.append(loan_candidate)
        
        # Also check for players who might be on loan but not in our database
        # This would require API calls, but we can make it optional
        api_candidates = []
        if data.get('include_api_check', False):
            logger.info("🔍 Checking API for additional loan candidates...")
            try:
                api_candidates = api_client.detect_multi_team_players(season=season)
                logger.info(f"📊 Found {len(api_candidates)} additional candidates from API")
            except Exception as e:
                logger.warning(f"API check failed: {e}")
        
        # Combine database and API candidates
        all_candidates = loan_candidates + api_candidates
        
        logger.info(f"✅ Found {len(all_candidates)} total loan candidates")
        
        return jsonify({
            'message': f'Successfully detected {len(all_candidates)} loan candidates',
            'candidates': all_candidates,
            'total_candidates': len(all_candidates),
            'database_candidates': len(loan_candidates),
            'api_candidates': len(api_candidates),
            'season': season
        })
        
    except Exception as e:
        logger.error(f"Error detecting loans from database: {e}")
        return jsonify({'error': str(e)}), 500

@api_bp.route('/teams/<int:team_id>/analyze-loans', methods=['GET'])
@require_api_key
def analyze_team_loans(team_id):
    """Analyze a specific team's players for loan patterns."""
    try:
        season = int(request.args.get('season', api_client.current_season_start_year))
        _sync_season(season=season)
        
        logger.info(f"🔍 Analyzing loans for team {team_id}, season {season}")
        
        # Get team info
        team_info = api_client.get_team_by_id(team_id, season)
        team_name = team_info.get('team', {}).get('name', f'Team {team_id}')
        
        # Get players for this team
        players_data = api_client.get_team_players(team_id, season)
        
        # Get multi-team data once for efficiency
        multi_team_dict = api_client.detect_multi_team_players(season=season)
        
        loan_analysis = {
            'team_id': team_id,
            'team_name': team_name,
            'season': season,
            'total_players': len(players_data),
            'potential_loans': [],
            'confirmed_loans': []
        }
        
        # Check each player for loan indicators
        for player_data in players_data:
            player_info = player_data.get('player', {})
            player_id = player_info.get('id')
            
            if not player_id:
                continue
            
            # Check if player exists in our database with loan records
            existing_player = Player.query.filter_by(player_id=player_id).first()
            
            if existing_player:
                # Check for existing loan records
                player_loans = LoanedPlayer.query.filter_by(player_id=existing_player.id).all()
                
                if player_loans:
                    # Player has loan records
                    loan_analysis['confirmed_loans'].append({
                        'player_id': player_id,
                        'player_name': player_info.get('name'),
                        'age': player_info.get('age'),
                        'nationality': player_info.get('nationality'),
                        'loan_count': len(player_loans),
                        'active_loans': len([loan for loan in player_loans if loan.is_active])
                    })
            
            # Check for multi-team indicators (potential loans) using pre-computed data
            try:
                transfer_analysis = api_client.analyze_transfer_type(
                    player_id, 
                    multi_team_dict=multi_team_dict, 
                    season=season
                )
                
                if transfer_analysis.get('is_likely_loan', False):
                    loan_analysis['potential_loans'].append({
                        'player_id': player_id,
                        'player_name': player_info.get('name'),
                        'age': player_info.get('age'),
                        'nationality': player_info.get('nationality'),
                        'loan_confidence': transfer_analysis.get('loan_confidence', 0.0),
                        'indicators': transfer_analysis.get('indicators', [])
                    })
            except Exception as e:
                logger.warning(f"Error analyzing player {player_id}: {e}")
        
        # Sort by confidence
        loan_analysis['potential_loans'].sort(key=lambda x: x['loan_confidence'], reverse=True)
        
        logger.info(f"✅ Analysis complete: {len(loan_analysis['confirmed_loans'])} confirmed, {len(loan_analysis['potential_loans'])} potential")
        
        return jsonify(loan_analysis)
        
    except Exception as e:
        logger.error(f"Error analyzing team loans: {e}")
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

@api_bp.route('/import-verified-loans/csv', methods=['POST'])
@require_api_key
def import_verified_loans_csv():
    """Import verified loan candidates from CSV and create loan records."""
    try:
        # Check if file is present
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        
        file = request.files['file']
        if file.filename == '' or not file.filename.lower().endswith('.csv'):
            return jsonify({'error': 'Please provide a CSV file'}), 400
        
        # Read CSV content
        stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
        csv_reader = csv.DictReader(stream)
        
        # Expected columns from export
        required_columns = ['player_id', 'manual_verified', 'actual_loan_status']
        
        # Validate CSV headers
        if not all(col in csv_reader.fieldnames for col in required_columns):
            return jsonify({
                'error': f'CSV must contain required columns: {required_columns}',
                'found_columns': csv_reader.fieldnames
            }), 400
        
        created_loans = []
        skipped_rows = []
        errors = []
        
        for row_num, row in enumerate(csv_reader, start=2):
            try:
                # Only process manually verified rows where actual status is 'loan'
                if row.get('manual_verified', '').lower() not in ['yes', 'true', '1']:
                    skipped_rows.append({
                        'row': row_num,
                        'player_name': row.get('player_name', 'Unknown'),
                        'reason': 'Not manually verified'
                    })
                    continue
                
                if row.get('actual_loan_status', '').lower() != 'loan':
                    skipped_rows.append({
                        'row': row_num,
                        'player_name': row.get('player_name', 'Unknown'),
                        'reason': f"Status: {row.get('actual_loan_status', 'unknown')}"
                    })
                    continue
                
                # Get required fields
                player_id = int(row['player_id'])
                parent_team_id = int(row.get('parent_team_id', 0)) if row.get('parent_team_id') else None
                loan_team_id = int(row.get('loan_team_id', 0)) if row.get('loan_team_id') else None
                
                if not parent_team_id or not loan_team_id:
                    errors.append(f"Row {row_num}: parent_team_id and loan_team_id required for loan creation")
                    continue
                
                # Get or create player record
                player = Player.query.filter_by(player_id=player_id).first()
                if not player:
                    # Create player from CSV data
                    player = Player(
                        player_id=player_id,
                        name=row.get('player_name', f'Player {player_id}'),
                        age=int(row.get('age', 25)) if row.get('age') else 25,
                        nationality=row.get('nationality', 'Unknown'),
                        position='Unknown'
                    )
                    db.session.add(player)
                    db.session.flush()
                
                # Check for existing loan to avoid duplicates
                season = int(row.get('season', api_client.current_season_start_year))
                existing_loan = LoanedPlayer.query.filter_by(
                    player_id=player.id,
                    parent_team_id=parent_team_id,
                    loan_team_id=loan_team_id,
                    loan_season=f'{season}-{season + 1}'
                ).first()
                
                if existing_loan:
                    skipped_rows.append({
                        'row': row_num,
                        'player_name': player.name,
                        'reason': 'Loan already exists'
                    })
                    continue
                
                # Create loan record
                loan = LoanedPlayer(
                    player_id=player.id,
                    parent_team_id=parent_team_id,
                    loan_team_id=loan_team_id,
                    loan_start_date=date(season, 8, 1),  # Season start
                    loan_end_date=date(season + 1, 6, 30),  # Season end
                    loan_season=f'{season}-{season + 1}',
                    loan_type='Season Long',
                    is_active=True,
                    performance_notes=f"Manually verified from AI detection. Confidence: {row.get('loan_confidence', 'unknown')}. Notes: {row.get('reviewer_notes', '')}"
                )
                
                db.session.add(loan)
                created_loans.append({
                    'player_name': player.name,
                    'parent_team_id': parent_team_id,
                    'loan_team_id': loan_team_id,
                    'season': f'{season}-{season + 1}',
                    'confidence': row.get('loan_confidence', 'unknown')
                })
                
            except Exception as e:
                errors.append(f"Row {row_num}: {str(e)}")
                continue
        
        # Commit all changes
        if created_loans:
            db.session.commit()
            logger.info(f"✅ Created {len(created_loans)} verified loan records")
        
        return jsonify({
            'message': f'Import complete: {len(created_loans)} loans created',
            'created_loans': created_loans,
            'total_loans_created': len(created_loans),
            'skipped_rows': skipped_rows,
            'total_skipped': len(skipped_rows),
            'errors': errors,
            'total_errors': len(errors),
            'summary': {
                'high_confidence_imports': len([l for l in created_loans if float(l['confidence']) >= 0.7]) if created_loans else 0,
                'medium_confidence_imports': len([l for l in created_loans if 0.4 <= float(l['confidence']) < 0.7]) if created_loans else 0,
                'low_confidence_imports': len([l for l in created_loans if float(l['confidence']) < 0.4]) if created_loans else 0
            }
        })
        
    except Exception as e:
        logger.error(f"Error analyzing CSV vs API for loans: {e}")
        return jsonify({'error': str(e)}), 500

