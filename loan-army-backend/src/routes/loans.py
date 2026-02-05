"""Loans blueprint for loan-related endpoints.

This blueprint handles:
- Loan listings and filtering
- Loan termination and performance updates
- CSV template download
- Loan flags (user-submitted corrections)
- Weekly loans report
"""

import csv
import io
import logging
from datetime import datetime, timezone

from flask import Blueprint, Response, jsonify, request
from werkzeug.exceptions import NotFound

from src.auth import require_api_key, get_client_ip, _safe_error_payload
from src.models.league import (
    db,
    LoanedPlayer,
    LoanFlag,
    SupplementalLoan,
    Team,
)

logger = logging.getLogger(__name__)

loans_bp = Blueprint('loans', __name__)


# Lazy import for api_client to avoid circular imports and early initialization
def _get_api_client():
    from src.routes.api import api_client
    return api_client


# Expose api_client as a module-level attribute for patching in tests
class _LazyApiClient:
    def __getattr__(self, name):
        return getattr(_get_api_client(), name)


api_client = _LazyApiClient()


# ---------------------------------------------------------------------------
# Loan listing endpoints
# ---------------------------------------------------------------------------

@loans_bp.route('/loans', methods=['GET'])
def get_loans():
    """Get all loans with optional filters.

    Query params:
    - season: Filter by season year
    - active_only: Filter to active loans only
    - loan_type: Filter by loan type
    - early_termination: Filter by early termination status
    - include_supplemental: Include supplemental loans
    """
    try:
        query = LoanedPlayer.query

        # Filter by season (derive from window_key prefix)
        season_val = request.args.get('season', type=int)
        if season_val:
            slug = f"{season_val}-{str(season_val + 1)[-2:]}"
            query = query.filter(LoanedPlayer.window_key.like(f"{slug}%"))

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

        loans = query.order_by(LoanedPlayer.updated_at.desc()).all()
        result = [loan.to_dict() for loan in loans]

        include_supp = request.args.get('include_supplemental', 'false').lower() in ('1', 'true', 'yes', 'on')
        if include_supp:
            supp_q = SupplementalLoan.query
            if season_val:
                supp_q = supp_q.filter(SupplementalLoan.season_year == season_val)
            supp_rows = supp_q.order_by(SupplementalLoan.updated_at.desc()).all()
            for s in supp_rows:
                try:
                    item = {
                        'player_name': s.player_name,
                        'primary_team_name': s.parent_team_name,
                        'primary_team_api_id': getattr(s.parent_team, 'team_id', None),
                        'loan_team_id': s.loan_team_id,
                        'loan_team_name': s.loan_team_name,
                        'loan_team_api_id': getattr(s.loan_team, 'team_id', None),
                        'window_key': f"{s.season_year}-{str(s.season_year + 1)[-2:]}",
                        'is_active': True,
                        'appearances': None,
                        'goals': None,
                        'assists': None,
                        'minutes_played': None,
                        'yellows': None,
                        'reds': None,
                        'data_source': s.data_source or 'supplemental',
                        'can_fetch_stats': False,
                        'created_at': s.created_at.isoformat() if s.created_at else None,
                        'updated_at': s.updated_at.isoformat() if s.updated_at else None,
                        'season_year': s.season_year,
                        'source': 'supplemental',
                    }
                    result.append(item)
                except Exception:
                    continue
        return jsonify(result)
    except Exception as e:
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500


@loans_bp.route('/loans/active', methods=['GET'])
def get_active_loans():
    """Get active loans."""
    try:
        loans = LoanedPlayer.query.filter_by(is_active=True).all()
        return jsonify([loan.to_dict() for loan in loans])
    except Exception as e:
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500


@loans_bp.route('/loans/season/<int:season>', methods=['GET'])
def get_loans_by_season(season: int):
    """Get all loans for a specific season (by window_key prefix)."""
    try:
        slug = f"{season}-{str(season + 1)[-2:]}"
        loans = LoanedPlayer.query.filter(LoanedPlayer.window_key.like(f"{slug}%")).all()
        return jsonify([loan.to_dict() for loan in loans])
    except Exception as e:
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500


# ---------------------------------------------------------------------------
# Weekly report endpoint
# ---------------------------------------------------------------------------

@loans_bp.route('/loans/weekly-report', methods=['GET'])
@require_api_key
def weekly_loans_report():
    """Weekly report summarising all active loanees from a parent club.

    Query parameters:
    - primary_team_id (int) [required]
    - season (int) [optional, default current]
    - from (YYYY-MM-DD) [required] week start
    - to (YYYY-MM-DD) [required] week end
    - include_team_stats [optional bool] include team statistics per match
    """
    try:
        from src.routes.api import resolve_team_ids

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

        # Infer season from 'from' date if not provided explicitly
        if season_param is None:
            season = week_start.year if week_start.month >= 8 else week_start.year - 1
        else:
            season = season_param

        db_id, api_id, team_name = resolve_team_ids(arg_team_id, season)
        if not db_id:
            return jsonify({'error': f'Team {arg_team_id} not found for season {season}'}), 404

        include_team_stats = request.args.get('include_team_stats', 'false').lower() in ('true', '1', 'yes', 'y')

        real_client = _get_api_client()
        real_client.set_season_year(season)
        real_client._prime_team_cache(season)

        report = real_client.summarize_parent_loans_week(
            parent_team_db_id=db_id,
            parent_team_api_id=api_id,
            season=season,
            week_start=week_start,
            week_end=week_end,
            include_team_stats=include_team_stats,
            db_session=db.session,
        )

        report['parent_team'] = {
            'id': api_id,
            'db_id': db_id,
            'name': team_name
        }

        db.session.commit()
        return jsonify(report)
    except Exception as e:
        logger.error(f"Error generating weekly loans report: {e}")
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500


# ---------------------------------------------------------------------------
# Loan management endpoints (admin)
# ---------------------------------------------------------------------------

@loans_bp.route('/loans/<int:loan_id>/terminate', methods=['POST'])
@require_api_key
def terminate_loan(loan_id):
    """Terminate a loan early."""
    try:
        loan = LoanedPlayer.query.get_or_404(loan_id)
        data = request.get_json() or {}

        termination_reason = data.get('reason', 'Not specified')
        termination_date = data.get('termination_date')

        if termination_date:
            try:
                termination_date = datetime.strptime(termination_date, '%Y-%m-%d').date()
            except ValueError:
                return jsonify({'error': 'Invalid date format. Use YYYY-MM-DD'}), 400
        else:
            termination_date = datetime.now(timezone.utc).date()

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
    except NotFound:
        raise
    except Exception as e:
        logger.error(f"Error terminating loan: {e}")
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500


@loans_bp.route('/loans/<int:loan_id>/performance', methods=['PUT'])
@require_api_key
def update_loan_performance(loan_id):
    """Update performance stats for a loan."""
    try:
        loan = LoanedPlayer.query.get_or_404(loan_id)
        data = request.get_json() or {}

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
    except NotFound:
        raise
    except Exception as e:
        logger.error(f"Error updating performance: {e}")
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500


# ---------------------------------------------------------------------------
# CSV template endpoint
# ---------------------------------------------------------------------------

@loans_bp.route('/loans/csv-template', methods=['GET'])
def get_csv_template():
    """Download CSV template for bulk loan upload."""
    try:
        output = io.StringIO()
        writer = csv.writer(output)

        headers = [
            'player_id', 'parent_team_id', 'loan_team_id', 'loan_start_date', 'loan_season',
            'loan_end_date', 'loan_type', 'loan_fee', 'buy_option_fee', 'recall_option',
            'appearances', 'goals', 'assists', 'minutes_played', 'performance_notes'
        ]
        writer.writerow(headers)

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

        return Response(
            csv_content,
            mimetype='text/csv',
            headers={'Content-Disposition': 'attachment; filename=loan_upload_template.csv'}
        )
    except Exception as e:
        logger.error(f"Error generating CSV template: {e}")
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500


# ---------------------------------------------------------------------------
# Loan flag endpoints (guest/admin)
# ---------------------------------------------------------------------------

@loans_bp.route('/loans/flags', methods=['POST'])
def create_loan_flag():
    """Create a loan flag (user-submitted correction)."""
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
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500


@loans_bp.route('/loans/flags/pending', methods=['GET'])
@require_api_key
def list_pending_flags():
    """List pending loan flags (admin only)."""
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
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500


@loans_bp.route('/loans/flags/<int:flag_id>/resolve', methods=['POST'])
@require_api_key
def resolve_flag(flag_id: int):
    """Resolve a loan flag (admin only)."""
    try:
        row = LoanFlag.query.get_or_404(flag_id)
        data = request.get_json() or {}
        action = (data.get('action') or '').strip()
        note = (data.get('note') or '').strip()

        deactivated = 0
        if action == 'deactivate_loan':
            season = row.season
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
        row.resolved_at = datetime.now(timezone.utc)
        db.session.commit()
        return jsonify({'message': 'Flag resolved', 'deactivated_loans': deactivated})
    except NotFound:
        raise
    except Exception as e:
        logger.exception('Error resolving flag')
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500
