from flask import Blueprint, request, jsonify, make_response, render_template, Response, current_app, g
from src.models.league import db, League, Team, LoanedPlayer, Newsletter, UserSubscription, EmailToken, LoanFlag, AdminSetting, NewsletterComment, UserAccount, _as_utc
from src.api_football_client import APIFootballClient
from datetime import datetime, date, timedelta, timezone
import uuid
import json
import logging
import csv
import io
import math
import re
import os
from functools import wraps
from uuid import uuid4
from sqlalchemy import or_
import time
from datetime import timedelta
from typing import Any
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
import secrets
import string
import requests
from src.extensions import limiter
from src.utils.sanitize import sanitize_comment_body, sanitize_plain_text
from src.agents.errors import NoActiveLoaneesError

logger = logging.getLogger(__name__)

api_bp = Blueprint('api', __name__)

# Initialize API-Football client
api_client = APIFootballClient()

SUBSCRIPTIONS_REQUIRE_VERIFY = os.getenv('SUBSCRIPTIONS_REQUIRE_VERIFY', '1').lower() in ('1', 'true', 'yes', 'on')
try:
    SUBSCRIPTIONS_VERIFY_TTL_MINUTES = int(os.getenv('SUBSCRIPTIONS_VERIFY_TTL_MINUTES') or 60 * 24)
except Exception:
    SUBSCRIPTIONS_VERIFY_TTL_MINUTES = 60 * 24


def _admin_email_list() -> list[str]:
    raw = os.getenv('ADMIN_EMAILS') or ''
    emails = [item.strip() for item in raw.split(',') if item.strip()]
    if not emails:
        return []
    # Preserve order while removing duplicates
    return list(dict.fromkeys(emails))

# API Key Authentication Decorator
def require_api_key(f):
    """Decorator to require API key for admin endpoints with optional IP whitelisting."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if request.method == 'OPTIONS':
            return make_response('', 204)
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
        if required_api_key:
            required_api_key = required_api_key.strip()
        
        if not required_api_key:
            logger.warning("ADMIN_API_KEY not configured in environment")
            return jsonify({
                'error': 'API authentication not configured',
                'message': 'Contact administrator'
            }), 500
        
        # Require admin Bearer token
        auth_header = request.headers.get('Authorization') or ''
        token_data = None
        if auth_header.startswith('Bearer '):
            token = auth_header.split(' ', 1)[1]
            try:
                data = _user_serializer().loads(token, max_age=60 * 60 * 24 * 30)
                if (data or {}).get('role') == 'admin':
                    token_data = data
                    g.user_email = (data or {}).get('email')
            except Exception as _e:
                logger.warning(f"Bearer admin token failed for {client_ip}: {_e}")

        if not token_data:
            logger.warning(f"Admin token missing or invalid for {client_ip}")
            return jsonify({'error': 'Admin login required', 'message': 'Provide a valid admin Bearer token'}), 401

        # Require API key as a second factor
        provided_key = request.headers.get('X-API-Key') or request.headers.get('X-Admin-Key')
        provided_key = (provided_key or '').strip()

        def _mask_admin_key(value: str | None) -> str:
            if not value:
                return '(none)'
            trimmed = value.strip()
            if len(trimmed) <= 6:
                return trimmed
            return f"{trimmed[:3]}...{trimmed[-3:]}"

        masked_key = _mask_admin_key(provided_key)

        if not provided_key:
            logger.warning(
                "Admin API key missing ip=%s user=%s endpoint=%s",
                client_ip,
                getattr(g, 'user_email', None),
                request.endpoint,
            )
            return jsonify({'error': 'Admin API key required', 'message': 'Send X-API-Key in the request headers'}), 401

        if provided_key != required_api_key:
            logger.warning(
                "Invalid admin credential ip=%s user=%s endpoint=%s key=%s",
                client_ip,
                getattr(g, 'user_email', None),
                request.endpoint,
                masked_key,
            )
            return jsonify({'error': 'Invalid admin credential', 'message': 'Access denied'}), 403

        logger.info(
            "Admin dual auth granted ip=%s user=%s endpoint=%s key=%s",
            client_ip,
            getattr(g, 'user_email', None),
            request.endpoint,
            masked_key,
        )
        return f(*args, **kwargs)
    
    return decorated_function

# CORS support
@api_bp.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization,X-API-Key,X-Admin-Key')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response


@api_bp.route('/admin/auth-check', methods=['GET'])
@require_api_key
def admin_auth_check():
    """Lightweight endpoint to verify admin credentials from the client UI."""
    return jsonify({
        'status': 'ok',
        'user': getattr(g, 'user_email', None),
    })

# --- Lightweight user token auth (for comments/login) ---
def _user_serializer() -> URLSafeTimedSerializer:
    secret = current_app.config.get('SECRET_KEY') or os.getenv('SECRET_KEY') or 'change-me'
    return URLSafeTimedSerializer(secret_key=secret, salt='user-auth')

# def _user_rate_limit_key() is defined near the top of this file to ensure it exists before decorator usage
def _base_display_name_from_email(email: str) -> str:
    local = (email or '').split('@')[0]
    cleaned = re.sub(r'[^a-zA-Z0-9]+', '', local)
    if not cleaned:
        cleaned = 'loaner'
    return cleaned[:16] or 'loaner'

def _make_display_name_unique(candidate: str) -> str:
    base = candidate[:28] or 'loaner'
    suffix = 1
    name = candidate
    while UserAccount.query.filter_by(display_name_lower=name.lower()).first():
        suffix += 1
        trim_base = base[: max(1, 30 - len(str(suffix)))]
        name = f"{trim_base}{suffix}"
    return name

def _generate_default_display_name(email: str) -> str:
    base = _base_display_name_from_email(email)
    candidate = base
    if len(candidate) < 3:
        candidate = f"{candidate}{'fan'}"
    candidate = candidate.title()
    return _make_display_name_unique(candidate)

def _normalize_display_name(value: str) -> str:
    cleaned = sanitize_plain_text(value or '')
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    cleaned = re.sub(r'[^A-Za-z0-9 ._\-]', '', cleaned)
    return cleaned[:40]

def _ensure_user_account(email: str) -> UserAccount:
    now = datetime.now(timezone.utc)
    user = UserAccount.query.filter_by(email=email).first()
    if user:
        user.last_login_at = now
        if not user.display_name:
            display_name = _generate_default_display_name(email)
            user.display_name = display_name
            user.display_name_lower = display_name.lower()
            user.display_name_confirmed = False
        if not user.last_display_name_change_at:
            user.last_display_name_change_at = now
        return user
    display_name = _generate_default_display_name(email)
    user = UserAccount(
        email=email,
        display_name=display_name,
        display_name_lower=display_name.lower(),
        display_name_confirmed=False,
        created_at=now,
        updated_at=now,
        last_login_at=now,
        last_display_name_change_at=now,
    )
    db.session.add(user)
    db.session.flush()
    return user

def issue_user_token(email: str, ttl_seconds: int = 60 * 60 * 24 * 30, role: str = 'user') -> dict:
    s = _user_serializer()
    # embed ts in payload for debugging; URLSafeTimedSerializer enforces max_age on loads
    payload = {'email': email, 'role': role, 'iat': int(time.time())}
    token = s.dumps(payload)
    logger.info("Issued auth token payload for %s with role=%s", email, role)
    return {
        'token': token,
        'expires_in': ttl_seconds
    }

def require_user_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.headers.get('Authorization', '')
        if auth.startswith('Bearer '):
            token = auth.split(' ', 1)[1]
        else:
            token = None
        if not token:
            return jsonify({'error': 'missing auth token'}), 401
        s = _user_serializer()
        try:
            # Accept tokens up to 30 days old by default
            data = s.loads(token, max_age=60 * 60 * 24 * 30)
            g.user_email = data.get('email')
        except SignatureExpired:
            return jsonify({'error': 'auth token expired'}), 401
        except BadSignature:
            return jsonify({'error': 'invalid auth token'}), 401
        return f(*args, **kwargs)
    return decorated


def _get_authorized_email() -> str | None:
    """Resolve the authenticated email from the current request, if present."""
    email = getattr(g, 'user_email', None)
    if email:
        return email

    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        token = auth_header.split(' ', 1)[1].strip()
        if token:
            serializer = _user_serializer()
            try:
                data = serializer.loads(token, max_age=60 * 60 * 24 * 30)
                resolved = (data or {}).get('email')
                if resolved:
                    g.user_email = resolved
                    return resolved
            except (SignatureExpired, BadSignature):
                return None
            except Exception:
                logger.exception('Failed to decode auth token while resolving email')
                return None
    return None

def _is_production() -> bool:
    env = (os.getenv('ENV') or os.getenv('FLASK_ENV') or os.getenv('APP_ENV') or '').strip().lower()
    return env in ('prod', 'production')

def _safe_error_payload(exc: Exception, fallback_message: str, include_detail: bool = False) -> dict[str, str]:
    """Return a sanitized error payload, hiding internal details in production."""
    payload = {'error': fallback_message}
    if include_detail or not _is_production():
        payload['detail'] = str(exc)
    else:
        reference = uuid4().hex[:8]
        payload['reference'] = reference
        logger.error('Error reference=%s: %s', reference, exc, exc_info=True)
    return payload

def _send_login_code(email: str, code: str):
    """Dev: print code to terminal; Prod: integrate with email provider (future).
    Never prints the code in production logs.
    """
    webhook_url = os.getenv('N8N_EMAIL_WEBHOOK_URL')
    method = (os.getenv('N8N_EMAIL_HTTP_METHOD') or 'POST').strip().upper()
    if method not in {'GET', 'POST'}:
        method = 'POST'

    expires_minutes = 5
    subject = 'Your Login Code'

    html_body = render_template(
        'login_code_email.html',
        email=email,
        code=code,
        expires_in=expires_minutes,
    )
    text_body = (
        f"Your Go On Loan login code is {code}. "
        f"It expires in {expires_minutes} minutes. "
        "If you did not request it, you can ignore this email."
    )

    if webhook_url:
        headers: dict[str, str] = {}
        if method == 'POST':
            headers['Content-Type'] = 'application/json'
        bearer = os.getenv('N8N_EMAIL_AUTH_BEARER')
        if bearer:
            headers['Authorization'] = f'Bearer {bearer}'

        payload = {
            'kind': 'login_code',
            'email': email,
            'code': code,
            'expires_in_minutes': expires_minutes,
            'subject': subject,
            'email': [email],
            'html': html_body,
            'text': text_body,
            'meta': {
                'from': {
                    'name': os.getenv('EMAIL_FROM_NAME', 'Go On Loan'),
                    'email': os.getenv('EMAIL_FROM_ADDRESS', 'no-reply@loan.army'),
                },
            },
        }

        request_kwargs: dict[str, Any]
        if method == 'GET':
            param_name = os.getenv('N8N_EMAIL_GET_PARAM', 'payload').strip() or 'payload'
            request_kwargs = {'params': {param_name: json.dumps(payload)}}
            request_fn = requests.get
        else:
            request_kwargs = {'json': payload}
            request_fn = requests.post

        try:
            resp = request_fn(webhook_url, headers=headers, timeout=10, **request_kwargs)
            if resp.status_code >= 300:
                logger.warning(
                    "Login webhook responded with non-2xx for %s status=%s body=%s",
                    email,
                    resp.status_code,
                    resp.text[:500] if isinstance(getattr(resp, 'text', ''), str) else '',
                )
            else:
                logger.info("Login code delivered via webhook for %s status=%s", email, resp.status_code)
        except Exception:
            logger.exception("Failed to call login webhook for %s", email)
    if not webhook_url or not _is_production():
        # In development, still surface the code for manual testing.
        msg = f"[DEV] Login code for {email}: {code} (expires in 5 minutes)"
        try:
            print(msg)
        except Exception:
            pass
        logger.info(msg)


def _send_email_via_webhook(
    *,
    email: str,
    subject: str,
    text: str,
    html: str | None = None,
    meta: dict | None = None,
    http_method_override: str | None = None,
) -> dict:
    webhook_url = os.getenv('N8N_EMAIL_WEBHOOK_URL')
    if not webhook_url:
        raise RuntimeError('N8N_EMAIL_WEBHOOK_URL is not configured')

    method = (http_method_override or os.getenv('N8N_EMAIL_HTTP_METHOD') or 'POST').strip().upper()
    if method not in {'GET', 'POST'}:
        method = 'POST'

    headers: dict[str, str] = {}
    if method == 'POST':
        headers['Content-Type'] = 'application/json'

    bearer = os.getenv('N8N_EMAIL_AUTH_BEARER')
    if bearer:
        headers['Authorization'] = f'Bearer {bearer}'

    payload = {
        'email': email,
        'subject': subject,
        'text': text,
        'html': html or text,
        'meta': meta or {},
    }

    try:
        if method == 'GET':
            param_name = os.getenv('N8N_EMAIL_GET_PARAM', 'payload').strip() or 'payload'
            response = requests.get(
                webhook_url,
                params={param_name: json.dumps(payload)},
                timeout=10,
            )
        else:
            response = requests.post(
                webhook_url,
                headers=headers,
                data=json.dumps(payload),
                timeout=10,
            )
        return {
            'status': 'ok' if response.ok else 'error',
            'http_status': response.status_code,
            'response_text': response.text,
        }
    except Exception as exc:
        logger.exception('Failed to send webhook email to %s', email)
        raise RuntimeError(f'Email delivery failed: {exc}') from exc


def _send_subscription_verification_email(email: str, team_names: list[str], token: str) -> dict:
    public_base = os.getenv('PUBLIC_BASE_URL', '').rstrip('/')
    confirm_path = f"/verify?token={token}"
    confirm_url = f"{public_base}{confirm_path}" if public_base else confirm_path

    subject = f"Confirm your newsletter subscription"

    team_lines_html = ''.join(f'<li>{name}</li>' for name in team_names)
    team_lines_text = '\n'.join(f" • {name}" for name in team_names)

    html = f"""
    <p>Thanks for subscribing to Go On Loan newsletters.</p>
    <p>Please confirm your email address to start receiving weekly updates.</p>
    <p><a href="{confirm_url}">Confirm subscription</a></p>
    <p>You requested updates for:</p>
    <ul>{team_lines_html}</ul>
    <p>If you did not make this request, you can ignore this message.</p>
    """
    text = (
        "Thanks for subscribing to Go On Loan newsletters.\n\n"
        "Confirm your email address to start receiving updates:\n"
        f"{confirm_url}\n\n"
        "You requested updates for:\n"
        f"{team_lines_text}\n\n"
        "If you did not make this request, you can ignore this message."
    )

    meta = {
        'kind': 'subscription_verification',
        'team_count': len(team_names),
    }
    return _send_email_via_webhook(email=email, subject=subject, text=text, html=html, meta=meta)

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

# -----------------
# Public auth flow
# -----------------

def _generate_otp_code(length: int = 11) -> str:
    """Generate a cryptographically-strong login code.
    Uses upper/lowercase letters, digits, and safe special symbols.
    """
    alphabet = string.ascii_letters + string.digits + "!@#$%^*-_"
    return ''.join(secrets.choice(alphabet) for _ in range(length))

@api_bp.route('/auth/request-code', methods=['POST'])
@limiter.limit("5 per minute", error_message="Too many login code requests. Please wait and try again.")
def request_login_code():
    email = None
    try:
        data = request.get_json() or {}
        email = (data.get('email') or '').strip().lower()
        if not email:
            logger.warning("Login code request missing email from %s", get_client_ip())
            return jsonify({'error': 'email is required'}), 400
        client_ip = get_client_ip()
        logger.info("Login code requested for %s from %s", email, client_ip)
        code = _generate_otp_code(11)
        # 5 minutes TTL
        tok = _create_email_token(email=email, purpose='login', metadata={'kind': 'otp'}, ttl_minutes=5)
        # Overwrite token string with numeric code so user types digits
        tok.token = code
        db.session.add(tok)
        db.session.commit()

        # Deliver or print locally depending on environment
        _send_login_code(email, code)
        logger.info("Login code issued for %s from %s (token_id=%s)", email, client_ip, tok.id)
        return jsonify({'message': 'Login code sent'})
    except Exception as e:
        logger.exception("Failed to issue login code for email=%s", email)
        try:
            db.session.rollback()
        except Exception:
            pass
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500

@api_bp.route('/auth/me', methods=['GET'])
@require_user_auth
def auth_me():
    try:
        auth = request.headers.get('Authorization', '')
        token = auth.split(' ', 1)[1] if auth.startswith('Bearer ') else None
        role = 'user'
        if token:
            try:
                data = _user_serializer().loads(token, max_age=60 * 60 * 24 * 30)
                role = (data or {}).get('role') or 'user'
            except Exception:
                pass
        email = getattr(g, 'user_email', None)
        user = UserAccount.query.filter_by(email=email).first() if email else None
        return jsonify({
            'email': email,
            'role': role,
            'user_id': user.id if user else None,
            'display_name': user.display_name if user else None,
            'display_name_confirmed': bool(user.display_name_confirmed) if user else False,
        })
    except Exception as e:
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500

def _user_rate_limit_key() -> str | None:
    return getattr(g, 'user_email', None) or (request.remote_addr or 'anon')

@api_bp.route('/auth/display-name', methods=['POST'])
@require_user_auth
@limiter.limit("3 per minute", key_func=_user_rate_limit_key)
def update_display_name():
    try:
        payload = request.get_json() or {}
        raw = (payload.get('display_name') or '').strip()
        normalized = _normalize_display_name(raw)
        if not normalized or len(normalized) < 3:
            return jsonify({'error': 'Display name must be at least 3 characters'}), 400
        if not re.match(r'^[A-Za-z0-9]', normalized):
            return jsonify({'error': 'Display name must start with a letter or number'}), 400
        email = getattr(g, 'user_email', None)
        if not email:
            return jsonify({'error': 'auth context missing email'}), 401
        user = UserAccount.query.filter_by(email=email).first()
        if not user:
            user = _ensure_user_account(email)
        lower = normalized.lower()
        now = datetime.now(timezone.utc)
        cooldown = timedelta(hours=24)
        if user.display_name_lower != lower:
            last_change = _as_utc(user.last_display_name_change_at) or _as_utc(user.updated_at) or _as_utc(user.created_at)
            enforce_cooldown = bool(user.display_name_confirmed)
            if enforce_cooldown and last_change and (now - last_change) < cooldown:
                remaining = cooldown - (now - last_change)
                hours = int(remaining.total_seconds() // 3600)
                minutes = int((remaining.total_seconds() % 3600) // 60)
                return jsonify({
                    'error': 'Display name recently updated. Try again later.',
                    'retry_after_seconds': int(remaining.total_seconds()),
                    'retry_after_human': f"{hours}h {minutes}m"
                }), 429
            conflict = UserAccount.query.filter(UserAccount.display_name_lower == lower, UserAccount.id != user.id).first()
            if conflict:
                return jsonify({'error': 'Display name already in use'}), 409
            user.display_name = normalized
            user.display_name_lower = lower
            user.display_name_confirmed = True
            user.last_display_name_change_at = now
            user.updated_at = now
        else:
            if not user.display_name_confirmed:
                user.display_name_confirmed = True
        db.session.commit()
        return jsonify({
            'message': 'Display name updated',
            'display_name': user.display_name,
            'display_name_confirmed': bool(user.display_name_confirmed),
        })
    except Exception as e:
        try:
            db.session.rollback()
        except Exception:
            pass
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500

@api_bp.route('/auth/verify-code', methods=['POST'])
@limiter.limit("10 per minute", error_message="Too many verification attempts. Please wait a moment and try again.")
def verify_login_code():
    email = None
    try:
        data = request.get_json() or {}
        email = (data.get('email') or '').strip().lower()
        code = (data.get('code') or '').strip()
        if not email or not code:
            logger.warning(
                "Verify-login missing fields email_present=%s code_present=%s from %s",
                bool(email),
                bool(code),
                get_client_ip(),
            )
            return jsonify({'error': 'email and code are required'}), 400
        client_ip = get_client_ip()
        logger.info("Verifying login code for %s from %s", email, client_ip)
        row = EmailToken.query.filter_by(email=email, token=code, purpose='login').first()
        if not row or not row.is_valid():
            logger.warning("Invalid/expired login code for %s from %s", email, client_ip)
            return jsonify({'error': 'invalid or expired code'}), 400
        # Mark used and issue an auth token
        row.used_at = datetime.now(timezone.utc)
        user = _ensure_user_account(email)
        if user:
            user.last_login_at = datetime.now(timezone.utc)
        db.session.commit()
        # Determine role by env allowlist
        allowed = [x.strip().lower() for x in (os.getenv('ADMIN_EMAILS') or '').split(',') if x.strip()]
        role = 'admin' if email in allowed else 'user'
        logger.info("Login verified for %s from %s role=%s", email, client_ip, role)
        out = issue_user_token(email, role=role)
        return jsonify({
            'message': 'Logged in',
            'role': role,
            'display_name': user.display_name if user else None,
            'display_name_confirmed': bool(user.display_name_confirmed) if user else False,
            **out,
        })
    except Exception as e:
        logger.exception("Failed to verify login code for email=%s", email)
        try:
            db.session.rollback()
        except Exception:
            pass
        return jsonify(_safe_error_payload(e, 'Unable to verify login code right now. Please try again later.')), 500
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
        # Append to run history for admin UI visibility
        try:
            ok = len([r for r in (result or []) if r.get("newsletter_id")])
            errs = len([r for r in (result or []) if r.get("error")])
            _append_run_history({
                "kind": "newsletter-run",
                "ran_for": target_dt.isoformat(),
                "ok": ok,
                "errors": errs,
                "message": f"Weekly newsletters run for {target_dt.isoformat()} ({ok} ok, {errs} errors)"
            })
        except Exception:
            pass
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
        # Append to run history
        try:
            ok = len([r for r in (result or []) if r.get("status") == "ok"])  # mcp variant shape
            errs = len([r for r in (result or []) if r.get("status") == "error"]) 
            _append_run_history({
                "kind": "newsletter-run-mcp",
                "ran_for": tdate.isoformat(),
                "ok": ok,
                "errors": errs,
                "message": f"Weekly newsletters (MCP) for {tdate.isoformat()} ({ok} ok, {errs} errors)"
            })
        except Exception:
            pass
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
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500

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
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500

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
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500

@api_bp.route('/teams/<int:team_id>/loans', methods=['GET'])
def get_team_loans(team_id):
    """Get loans for a specific team."""
    try:
        team = Team.query.get_or_404(team_id)
        loans = LoanedPlayer.query.filter_by(primary_team_id=team.id).all()
        return jsonify([loan.to_dict() for loan in loans])
    except Exception as e:
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500

@api_bp.route('/teams/<int:team_id>/loans/season/<int:season>', methods=['GET'])
def get_team_loans_by_season(team_id: int, season: int):
    """Get loans for a specific team in a specific season (by window_key prefix)."""
    try:
        team = Team.query.get_or_404(team_id)
        slug = f"{season}-{str(season + 1)[-2:]}"
        active_only = (request.args.get('active_only', 'false').lower() in ('true', '1', 'yes', 'y'))
        q = (
            LoanedPlayer.query
            .filter(LoanedPlayer.primary_team_id == team.id)
            .filter(LoanedPlayer.window_key.like(f"{slug}%"))
        )
        if active_only:
            q = q.filter(LoanedPlayer.is_active.is_(True))
        loans = q.order_by(LoanedPlayer.updated_at.desc()).all()
        return jsonify([loan.to_dict() for loan in loans])
    except Exception as e:
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500

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
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500

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
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500

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
        return jsonify([loan.to_dict() for loan in loans])
    except Exception as e:
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500

@api_bp.route('/loans/active', methods=['GET'])
def get_active_loans():
    """Get active loans."""
    try:
        loans = LoanedPlayer.query.filter_by(is_active=True).all()
        return jsonify([loan.to_dict() for loan in loans])
    except Exception as e:
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500

@api_bp.route('/loans/season/<int:season>', methods=['GET'])
def get_loans_by_season(season: int):
    """Get all loans for a specific season (by window_key prefix)."""
    try:
        slug = f"{season}-{str(season + 1)[-2:]}"
        loans = LoanedPlayer.query.filter(LoanedPlayer.window_key.like(f"{slug}%")).all()
        return jsonify([loan.to_dict() for loan in loans])
    except Exception as e:
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500

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
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500

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
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500

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
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500

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
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500

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

        # Filter by multiple teams (comma-separated list)
        raw_team_ids = request.args.get('team_ids')
        if raw_team_ids:
            try:
                ids = [int(x.strip()) for x in str(raw_team_ids).split(',') if str(x).strip().isdigit()]
                if ids:
                    query = query.filter(Newsletter.team_id.in_(ids))
            except Exception:
                pass
        
        # Filter by newsletter type
        newsletter_type = request.args.get('type')
        if newsletter_type:
            query = query.filter_by(newsletter_type=newsletter_type)

        # Filter by league (by leagues PK)
        league_id = request.args.get('league_id', type=int)
        if league_id:
            query = query.join(Team).filter(Team.league_id == league_id)
        
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
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500

@api_bp.route('/subscriptions/me', methods=['GET'])
@require_user_auth
def my_subscriptions():
    """Return active subscriptions for the authenticated user's email."""
    try:
        email = getattr(g, 'user_email', None)
        email_norm = (email or '').strip().lower()
        if not email_norm:
            return jsonify({'error': 'Unauthorized'}), 401
        subs = UserSubscription.query.filter_by(email=email_norm, active=True).all()
        return jsonify([s.to_dict() for s in subs])
    except Exception as e:
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500


@api_bp.route('/subscriptions/me', methods=['POST'])
@require_user_auth
def update_my_subscriptions():
    """Create, reactivate, or deactivate team subscriptions for the signed-in user."""
    try:
        email = getattr(g, 'user_email', None)
        if not email:
            return jsonify({'error': 'Unauthorized'}), 401

        payload = request.get_json() or {}
        team_ids_raw = payload.get('team_ids') or []
        preferred_frequency = (payload.get('preferred_frequency') or 'weekly').strip() or 'weekly'

        parsed_ids: list[int] = []
        rejected_inputs: list[Any] = []
        for raw in team_ids_raw:
            try:
                tid = int(raw)
            except (TypeError, ValueError):
                rejected_inputs.append(raw)
                continue
            parsed_ids.append(tid)

        # Preserve order but drop duplicates
        unique_ids: list[int] = []
        seen: set[int] = set()
        for tid in parsed_ids:
            if tid not in seen:
                seen.add(tid)
                unique_ids.append(tid)

        team_rows = Team.query.filter(Team.id.in_(unique_ids)).all() if unique_ids else []
        valid_ids = {row.id for row in team_rows}
        missing_team_ids = [tid for tid in unique_ids if tid not in valid_ids]

        desired_team_ids = set(valid_ids)
        email_norm = (email or '').strip().lower()
        now = datetime.now(timezone.utc)

        existing_rows = UserSubscription.query.filter_by(email=email_norm).all()
        existing_map = {row.team_id: row for row in existing_rows}

        created_count = 0
        reactivated_count = 0
        updated_pref_count = 0

        for team in team_rows:
            sub = existing_map.get(team.id)
            if sub:
                changed = False
                if not sub.active:
                    sub.active = True
                    changed = True
                    reactivated_count += 1
                if sub.preferred_frequency != preferred_frequency:
                    sub.preferred_frequency = preferred_frequency
                    changed = True
                    updated_pref_count += 1
                if not sub.unsubscribe_token:
                    sub.unsubscribe_token = str(uuid.uuid4())
                    changed = True
                if changed:
                    sub.updated_at = now
            else:
                subscription = UserSubscription(
                    email=email_norm,
                    team_id=team.id,
                    preferred_frequency=preferred_frequency,
                    active=True,
                    unsubscribe_token=str(uuid.uuid4()),
                    created_at=now,
                    updated_at=now,
                )
                db.session.add(subscription)
                created_count += 1

        deactivated_count = 0
        for sub in existing_rows:
            if sub.team_id not in desired_team_ids and sub.active:
                sub.active = False
                sub.updated_at = now
                deactivated_count += 1

        db.session.commit()

        active_subs = UserSubscription.query.filter_by(email=email_norm, active=True).all()
        response = {
            'message': 'Subscriptions updated',
            'created_count': created_count,
            'reactivated_count': reactivated_count,
            'updated_frequency_count': updated_pref_count,
            'deactivated_count': deactivated_count,
            'ignored_team_ids': missing_team_ids + rejected_inputs,
            'subscriptions': [s.to_dict() for s in active_subs],
        }
        return jsonify(response)
    except Exception as e:
        try:
            db.session.rollback()
        except Exception:
            pass
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500

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

        try:
            comments = (
                NewsletterComment.query
                .filter_by(newsletter_id=newsletter_id, is_deleted=False)
                .order_by(NewsletterComment.created_at.asc())
                .all()
            )
            payload['comments'] = [comment.to_dict() for comment in comments]
        except Exception:
            payload['comments'] = []

        return jsonify(payload)
    except Exception as e:
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500

@api_bp.route('/newsletters/<int:newsletter_id>/comments', methods=['GET'])
def list_newsletter_comments(newsletter_id: int):
    try:
        # Ensure newsletter exists
        Newsletter.query.get_or_404(newsletter_id)
        rows = NewsletterComment.query\
            .filter_by(newsletter_id=newsletter_id, is_deleted=False)\
            .order_by(NewsletterComment.created_at.asc())\
            .all()
        return jsonify([r.to_dict() for r in rows])
    except Exception as e:
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500

@api_bp.route('/newsletters/<int:newsletter_id>/comments', methods=['POST'])
@require_user_auth
@limiter.limit("8 per minute", key_func=_user_rate_limit_key)
def create_newsletter_comment(newsletter_id: int):
    try:
        nl = Newsletter.query.get_or_404(newsletter_id)
        payload = request.get_json() or {}
        raw_body = (payload.get('body') or '').strip()
        if not raw_body:
            return jsonify({'error': 'body is required'}), 400
        body = sanitize_comment_body(raw_body)
        user_email = getattr(g, 'user_email', None)
        if not user_email:
            return jsonify({'error': 'auth context missing email'}), 401
        user = UserAccount.query.filter_by(email=user_email).first()
        if not user:
            user = _ensure_user_account(user_email)
        if not body:
            return jsonify({'error': 'body is required'}), 400
        c = NewsletterComment(
            newsletter_id=nl.id,
            user_id=user.id if user else None,
            author_email=user_email,
            author_name=user.display_name if user else None,
            author_name_legacy=user.display_name if user else None,
            user=user,
            body=body,
        )
        if not c.author_email:
            return jsonify({'error': 'auth context missing email'}), 401
        db.session.add(c)
        db.session.commit()
        return jsonify({'message': 'Comment created', 'comment': c.to_dict()}), 201
    except Exception as e:
        try:
            db.session.rollback()
        except Exception:
            pass
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500

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
        
        # For weekly newsletters, use the OpenAI-powered generator which
        # compiles full player + loan team weekly context before writing,
        # then persist the newsletter with the same semantics as before.
        if newsletter_type == 'weekly':
            from src.agents.weekly_newsletter_agent import (
                compose_team_weekly_newsletter,
                persist_newsletter,
            )

            composed = compose_team_weekly_newsletter(team_id, target_date)
            # Persist using shared helper (sets generated_date/published_date)
            row = persist_newsletter(
                team_db_id=team_id,
                content_json_str=composed['content_json'],
                week_start=composed['week_start'],
                week_end=composed['week_end'],
                issue_date=target_date,
                newsletter_type='weekly',
            )
            return jsonify({
                'message': 'Newsletter generated successfully',
                'newsletter': row.to_dict()
            })
        
        # Fallback for other types (currently unsupported):
        return jsonify({'error': f'Unsupported newsletter type: {newsletter_type}'}), 400
        
    except Exception as e:
        # Ensure DB session is not left in a failed state for subsequent requests
        try:
            db.session.rollback()
        except Exception:
            pass
        logger.error(f"Error generating newsletter: {e}")
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500

def generate_newsletter_content(*args, **kwargs):  # pragma: no cover - legacy shim
    """Deprecated: shim retained for backward compatibility.
    The /newsletters/generate endpoint now uses the OpenAI-backed
    generator for 'weekly' type. This function is unused and will
    be removed in a future cleanup.
    """
    raise NotImplementedError("Legacy mock generator removed; use generate_team_weekly_newsletter")

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
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500


def _activate_subscriptions(email: str, team_ids: list[int], preferred_frequency: str = 'weekly') -> dict[str, Any]:
    created_ids: list[int] = []
    updated_ids: list[int] = []
    skipped: list[dict[str, Any]] = []

    unique_ids: list[int] = []
    seen_ids: set[int] = set()
    for tid in team_ids:
        if tid in seen_ids:
            continue
        seen_ids.add(tid)
        unique_ids.append(tid)

    team_rows = Team.query.filter(Team.id.in_(unique_ids)).all() if unique_ids else []
    team_map = {row.id: row for row in team_rows}

    for tid in unique_ids:
        team = team_map.get(tid)
        if not team:
            skipped.append({'team_id': tid, 'reason': 'team not found'})
            continue

        existing = UserSubscription.query.filter_by(email=email, team_id=team.id).first()
        if existing:
            changed = False
            if not existing.active:
                existing.active = True
                changed = True
            if existing.preferred_frequency != preferred_frequency:
                existing.preferred_frequency = preferred_frequency
                changed = True
            if not existing.unsubscribe_token:
                existing.unsubscribe_token = str(uuid.uuid4())
                changed = True
            if changed:
                updated_ids.append(existing.id)
            else:
                skipped.append({'team_id': team.id, 'reason': 'already active'})
            continue

        subscription = UserSubscription(
            email=email,
            team_id=team.id,
            preferred_frequency=preferred_frequency,
            active=True,
            unsubscribe_token=str(uuid.uuid4()),
        )
        db.session.add(subscription)
        db.session.flush()
        created_ids.append(subscription.id)

    result_ids = created_ids + updated_ids
    subs = UserSubscription.query.filter(UserSubscription.id.in_(result_ids)).all() if result_ids else []

    return {
        'message': 'Subscriptions updated',
        'created_count': len(created_ids),
        'updated_count': len(updated_ids),
        'skipped': skipped,
        'created_ids': created_ids,
        'updated_ids': updated_ids,
        'subscriptions': [s.to_dict() for s in subs],
    }


def _process_subscriptions(email: str, team_ids_raw: list[Any], preferred_frequency: str) -> tuple[dict[str, Any], int]:
    if not email:
        return {'error': 'email is required'}, 400
    if not team_ids_raw:
        return {'error': 'team_ids are required'}, 400

    parsed_ids: list[int] = []
    skipped: list[dict[str, Any]] = []
    for raw_id in team_ids_raw:
        try:
            tid = int(raw_id)
        except (TypeError, ValueError):
            skipped.append({'team_id': raw_id, 'reason': 'invalid team id'})
            continue
        parsed_ids.append(tid)

    if not parsed_ids:
        return {'error': 'No valid team ids provided', 'skipped': skipped}, 400

    team_rows = Team.query.filter(Team.id.in_(parsed_ids)).all()
    team_map = {row.id: row for row in team_rows}

    valid_ids: list[int] = []
    team_names: list[str] = []
    seen_ids: set[int] = set()
    for tid in parsed_ids:
        if tid in seen_ids:
            continue
        seen_ids.add(tid)
        team = team_map.get(tid)
        if not team:
            skipped.append({'team_id': tid, 'reason': 'team not found'})
            continue
        valid_ids.append(tid)
        team_names.append(team.name or f'Team #{tid}')

    if not valid_ids:
        return {'error': 'No valid team ids provided', 'skipped': skipped}, 400

    if SUBSCRIPTIONS_REQUIRE_VERIFY:
        try:
            token_row = _create_email_token(
                email=email,
                purpose='subscribe_confirm',
                metadata={'team_ids': valid_ids, 'preferred_frequency': preferred_frequency},
                ttl_minutes=SUBSCRIPTIONS_VERIFY_TTL_MINUTES,
            )
            db.session.flush()
            _send_subscription_verification_email(email, team_names, token_row.token)
            db.session.commit()
            return ({
                'message': 'Verification email sent. Please check your inbox to confirm.',
                'verification_required': True,
                'team_count': len(valid_ids),
                'expires_at': token_row.expires_at.isoformat() if token_row.expires_at else None,
                'skipped': skipped,
            }, 202)
        except Exception as exc:
            try:
                db.session.rollback()
            except Exception:
                pass
            logger.exception('Failed to queue subscription verification for %s', email)
            return _safe_error_payload(exc, 'Failed to send verification email'), 500

    result = _activate_subscriptions(email, valid_ids, preferred_frequency)
    result['skipped'].extend(skipped)
    db.session.commit()
    status = 201 if result['created_count'] else 200
    return result, status

@api_bp.route('/subscriptions', methods=['POST'])
def create_subscription():
    """Create a new subscription for a single team."""
    try:
        data = request.get_json() or {}

        email = data.get('email')
        team_id = data.get('team_id')
        preferred_frequency = data.get('preferred_frequency', 'weekly')

        if not email or team_id is None:
            return jsonify({'error': 'email and team_id are required'}), 400

        payload, status = _process_subscriptions(email, [team_id], preferred_frequency)
        return jsonify(payload), status
    except Exception as e:
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500

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

        payload, status = _process_subscriptions(email, team_ids, preferred_frequency)
        return jsonify(payload), status
    except Exception as e:
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500

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
    logger.info(
        "Created email token id=%s purpose=%s email=%s expires_at=%s",
        row.id,
        purpose,
        email,
        expires_at.isoformat(),
    )
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
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500

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
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500

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
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500


@api_bp.route('/subscriptions/unsubscribe', methods=['POST'])
def unsubscribe_by_email():
    """Unsubscribe an email address from one or more teams."""
    try:
        payload = request.get_json() or {}
        email_raw = payload.get('email')
        email = (email_raw or '').strip().lower()
        team_ids = payload.get('team_ids') or []

        if not email:
            auth_email = _get_authorized_email()
            if auth_email:
                email = auth_email.strip().lower()

        if not email:
            return jsonify({'error': 'email is required'}), 400

        query = UserSubscription.query.filter_by(email=email)
        parsed_ids: set[int] = set()
        for raw in team_ids:
            try:
                parsed_ids.add(int(raw))
            except (TypeError, ValueError):
                continue
        if parsed_ids:
            query = query.filter(UserSubscription.team_id.in_(parsed_ids))

        subs = query.all()
        if not subs:
            return jsonify({'message': 'No matching subscriptions found', 'count': 0}), 200

        count = 0
        for sub in subs:
            if sub.active:
                sub.active = False
                count += 1
        db.session.commit()
        return jsonify({'message': 'Unsubscribed successfully', 'count': count})
    except Exception as e:
        try:
            db.session.rollback()
        except Exception:
            pass
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500


def _unsubscribe_subscription_by_token(token: str) -> tuple[UserSubscription | None, str, int]:
    token = (token or '').strip()
    if not token:
        return None, 'missing_token', 400

    sub = UserSubscription.query.filter_by(unsubscribe_token=token).first()
    if not sub:
        return None, 'not_found', 404

    if sub.active:
        try:
            sub.active = False
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise
        return sub, 'unsubscribed', 200

    return sub, 'already_unsubscribed', 200


def _public_manage_url() -> str | None:
    base = os.getenv('PUBLIC_BASE_URL', '').rstrip('/')
    if not base:
        return None
    manage_path = os.getenv('PUBLIC_MANAGE_PATH', '/manage')
    return f"{base}{manage_path}"


@api_bp.route('/subscriptions/unsubscribe/<token>', methods=['GET', 'POST'])
def token_unsubscribe(token: str):
    """Unsubscribe a single subscription by its unsubscribe token.

    POST returns JSON for programmatic callers. GET immediately unsubscribes
    and renders a lightweight confirmation page suitable for email links.
    """
    if request.method == 'POST':
        try:
            sub, status, code = _unsubscribe_subscription_by_token(token)
        except Exception as e:
            logger.exception('Error unsubscribing via token (POST)')
            return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500

        if status == 'missing_token':
            return jsonify({'error': 'token is required'}), code
        if status == 'not_found':
            return jsonify({'error': 'invalid token'}), code

        message = 'Unsubscribed successfully' if status == 'unsubscribed' else 'Subscription already inactive'
        return jsonify({'message': message}), code

    # GET: render confirmation page
    try:
        sub, status, code = _unsubscribe_subscription_by_token(token)
    except Exception as e:
        logger.exception('Error unsubscribing via token (GET)')
        error_ctx = {
            'status': 'error',
            'headline': 'Something went wrong',
            'body': 'We were unable to process your unsubscribe request. Please try again later.',
            'manage_url': _public_manage_url(),
        }
        return render_template('unsubscribe_confirmation.html', **error_ctx), 500

    manage_url = _public_manage_url()
    team_name = sub.team.name if sub and getattr(sub, 'team', None) else None

    if status == 'missing_token':
        ctx = {
            'status': 'error',
            'headline': 'Invalid unsubscribe link',
            'body': 'The unsubscribe link is missing required information. Please check the email and try again.',
            'manage_url': manage_url,
            'team_name': team_name,
        }
    elif status == 'not_found':
        ctx = {
            'status': 'error',
            'headline': 'Link expired or invalid',
            'body': 'We could not find a subscription for this link. It may have already been used or expired.',
            'manage_url': manage_url,
            'team_name': team_name,
        }
    elif status == 'unsubscribed':
        ctx = {
            'status': 'ok',
            'headline': 'You are unsubscribed',
            'body': 'You will no longer receive updates for this team. You can manage other preferences anytime.',
            'manage_url': manage_url,
            'team_name': team_name,
            'email': sub.email if sub else None,
        }
    else:  # already_unsubscribed
        ctx = {
            'status': 'ok',
            'headline': 'Already unsubscribed',
            'body': 'This email was already unsubscribed from this team. No further action is required.',
            'manage_url': manage_url,
            'team_name': team_name,
            'email': sub.email if sub else None,
        }

    return render_template('unsubscribe_confirmation.html', **ctx), code

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
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500

@api_bp.route('/verify/<token>', methods=['POST'])
def verify_email_token(token: str):
    """Mark verification token as used; handles generic verification and subscription confirmation."""
    try:
        row = EmailToken.query.filter_by(token=token).first()
        if not row or not row.is_valid():
            return jsonify({'error': 'invalid or expired token'}), 400

        purpose = (row.purpose or '').strip().lower()
        if purpose == 'subscribe_confirm':
            meta = {}
            try:
                meta = json.loads(row.metadata_json or '{}')
            except Exception:
                meta = {}
            team_ids_raw = meta.get('team_ids') or []
            preferred_frequency = meta.get('preferred_frequency', 'weekly')
            try:
                team_ids = [int(tid) for tid in team_ids_raw]
            except Exception:
                team_ids = []
            if not team_ids:
                return jsonify({'error': 'Token metadata missing team ids'}), 400
            result = _activate_subscriptions(row.email, team_ids, preferred_frequency)
            row.used_at = datetime.now(timezone.utc)
            db.session.commit()
            status = 201 if result['created_count'] else 200
            return jsonify({
                'message': 'Subscriptions confirmed',
                'email': row.email,
                **result,
            }), status

        if purpose == 'verify':
            row.used_at = datetime.now(timezone.utc)
            db.session.commit()
            return jsonify({'message': 'Email verified', 'email': row.email})

        return jsonify({'error': f'Unsupported token purpose: {purpose or "unknown"}'}), 400
    except Exception as e:
        try:
            db.session.rollback()
        except Exception:
            pass
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500

@api_bp.route('/subscriptions/<int:subscription_id>', methods=['DELETE'])
def delete_subscription(subscription_id):
    """Unsubscribe from newsletter."""
    try:
        subscription = UserSubscription.query.get_or_404(subscription_id)
        subscription.active = False
        db.session.commit()
        
        return jsonify({'message': 'Unsubscribed successfully'})
    except Exception as e:
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500

# Statistics endpoints
@api_bp.route('/stats/overview', methods=['GET'])
def get_overview_stats():
    """Get overview statistics."""
    try:
        # current_season e.g. "2025-26"; also have start-year
        current_season_slug = api_client.current_season
        season_start_year = api_client.current_season_start_year
        if not current_season_slug and season_start_year:
            current_season_slug = f"{season_start_year}-{str(season_start_year + 1)[-2:]}"

        # Distinct teams with active loans (use correct column name)
        teams_with_active_loans = (
            db.session.query(LoanedPlayer.primary_team_id)
            .filter(LoanedPlayer.is_active.is_(True))
            .distinct()
            .count()
        )

        season_loans_count = 0
        if current_season_slug:
            season_loans_count = LoanedPlayer.query.filter(
                LoanedPlayer.window_key.like(f"{current_season_slug}%")
            ).count()

        stats = {
            'total_teams': Team.query.filter_by(is_active=True).count(),
            'european_leagues': League.query.filter_by(is_european_top_league=True).count(),
            'total_active_loans': LoanedPlayer.query.filter_by(is_active=True).count(),
            'season_loans': season_loans_count,
            'early_terminations': 0,
            'teams_with_loans': teams_with_active_loans,
            'total_subscriptions': UserSubscription.query.filter_by(active=True).count() if hasattr(UserSubscription, 'active') else UserSubscription.query.count(),
            'total_newsletters': Newsletter.query.filter_by(published=True).count(),
            'current_season': current_season_slug
        }
        return jsonify(stats)
    except Exception as e:
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500

@api_bp.route('/stats/loans', methods=['GET'])
def get_loan_stats():
    """Get detailed loan statistics."""
    try:
        current_season_slug = api_client.current_season
        season_start_year = api_client.current_season_start_year
        if not current_season_slug and season_start_year:
            current_season_slug = f"{season_start_year}-{str(season_start_year + 1)[-2:]}"

        base_q = LoanedPlayer.query
        if current_season_slug:
            base_q = base_q.filter(LoanedPlayer.window_key.like(f"{current_season_slug}%"))

        total_season = base_q.count()
        active = base_q.filter(LoanedPlayer.is_active.is_(True)).count()
        completed = base_q.filter(LoanedPlayer.is_active.is_(False)).count()

        stats = {
            'current_season': current_season_slug,
            'loan_types': [],
            'termination_reasons': [],
            'total_season_loans': total_season,
            'active_loans': active,
            'completed_loans': completed,
            'early_terminations': 0
        }
        
        return jsonify(stats)
    except Exception as e:
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500

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
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500

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
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500

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
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500

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
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500

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
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500

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

# --- Newsletter delivery helpers ---
def _newsletter_render_context(n: Newsletter) -> dict[str, Any]:
    data = _load_newsletter_json(n) or {}
    return {
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

def _deliver_newsletter_via_webhook(
    n: Newsletter,
    *,
    recipients: list[str] | None = None,
    subject_override: str | None = None,
    webhook_url_override: str | None = None,
    http_method_override: str | None = None,
    dry_run: bool = False,
) -> dict:
    """Render newsletter to HTML/TXT and POST to n8n webhook.
    Returns dict with 'status', 'http_status', and 'recipient_count'.
    """
    # Resolve webhook URL and headers
    webhook_url = webhook_url_override or os.getenv('N8N_EMAIL_WEBHOOK_URL')
    if not webhook_url:
        raise RuntimeError('N8N_EMAIL_WEBHOOK_URL is not configured')
    method = (http_method_override or os.getenv('N8N_EMAIL_HTTP_METHOD') or 'POST').strip().upper()
    if method not in {'GET', 'POST'}:
        method = 'POST'

    headers = {}
    if method == 'POST':
        headers['Content-Type'] = 'application/json'
    bearer = os.getenv('N8N_EMAIL_AUTH_BEARER')
    if bearer:
        headers['Authorization'] = f'Bearer {bearer}'

    team_ids: list[int] = []
    if n.team_id:
        try:
            team_ids.append(int(n.team_id))
        except (TypeError, ValueError):
            pass

    team_api_id = None
    if getattr(n, 'team', None) is not None:
        team_api_id = getattr(n.team, 'team_id', None)
    if team_api_id is None and n.team_id:
        try:
            team_row = Team.query.with_entities(Team.team_id).filter(Team.id == n.team_id).first()
            if team_row:
                team_api_id = team_row[0]
        except Exception:
            team_api_id = None

    if team_api_id is not None:
        try:
            alt_ids = (
                Team.query.with_entities(Team.id)
                .filter(Team.team_id == team_api_id)
                .all()
            )
            team_ids.extend(int(row[0]) for row in alt_ids if row and row[0])
        except Exception:
            pass

    team_ids = list(dict.fromkeys(team_ids))

    if team_ids:
        subs = (
            UserSubscription.query
            .filter(UserSubscription.active.is_(True))
            .filter(UserSubscription.team_id.in_(team_ids))
            .all()
        )
    else:
        subs = []

    def _normalize_email(value: str | None) -> str:
        return (value or '').strip().lower()

    sub_lookup: dict[str, UserSubscription] = {}
    ordered_sub_emails: list[str] = []
    for s in subs:
        if s.email_bounced:
            continue
        raw_email = (s.email or '').strip()
        key = _normalize_email(raw_email)
        if not raw_email or not key:
            continue
        if key not in sub_lookup:
            sub_lookup[key] = s
            ordered_sub_emails.append(raw_email)

    # Gather recipients from active team subscriptions if not provided
    if recipients is None:
        recipients = ordered_sub_emails

    recipients = [r for r in (recipients or []) if (r or '').strip()]
    total_recipients = len(recipients)
    if total_recipients == 0:
        return {
            'status': 'no_recipients',
            'http_status': None,
            'recipient_count': 0,
            'webhook_url': webhook_url,
            'response_text': '',
        }

    # Render content
    ctx = _newsletter_render_context(n)
    text_base = _plain_text_from_news(_load_newsletter_json(n) or {}, n)
    subject = subject_override or (ctx['title'] or 'Weekly Loan Update')

    from_addr = {
        'name': os.getenv('EMAIL_FROM_NAME', 'Go On Loan'),
        'email': os.getenv('EMAIL_FROM_ADDRESS', 'no-reply@loan.army'),
    }

    # Optional public base URL for manage/unsubscribe links if the n8n flow uses it
    public_base = os.getenv('PUBLIC_BASE_URL', '').rstrip('/')
    link_base = os.getenv('NEWSLETTER_LINK_BASE_URL', '').rstrip('/')
    unsubscribe_base = (
        link_base
        or os.getenv('PUBLIC_UNSUBSCRIBE_BASE_URL', '').rstrip('/')
        or os.getenv('PUBLIC_API_BASE_URL', '').rstrip('/')
        or public_base
    )
    manage_url = _public_manage_url()

    meta_base = {
        'issue_date': n.issue_date.isoformat() if n.issue_date else None,
        'week_start': n.week_start_date.isoformat() if n.week_start_date else None,
        'week_end': n.week_end_date.isoformat() if n.week_end_date else None,
        'public_base_url': public_base or None,
        'dry_run': bool(dry_run),
    }

    delivered_count = 0
    failures: list[dict[str, Any]] = []
    last_status_code: int | None = None
    last_response_text = ''

    for email in recipients:
        normalized_email = _normalize_email(email)
        subscription = sub_lookup.get(normalized_email)
        unsubscribe_url = None
        if subscription and subscription.unsubscribe_token:
            token_path = f"/subscriptions/unsubscribe/{subscription.unsubscribe_token}"
            if unsubscribe_base:
                unsubscribe_url = f"{unsubscribe_base.rstrip('/')}{token_path}"
            else:
                unsubscribe_url = token_path

        html = render_template(
            'newsletter_email.html',
            **ctx,
            unsubscribe_url=unsubscribe_url,
            manage_url=manage_url,
        )

        text = text_base
        if unsubscribe_url:
            text = f"{text_base}\n\nTo unsubscribe from this team, visit: {unsubscribe_url}\n"

        meta_payload = meta_base.copy()
        meta_payload.update({
            'unsubscribe_url': unsubscribe_url,
            'subscription_id': subscription.id if subscription else None,
            'manage_url': manage_url,
        })

        payload = {
            'newsletter_id': n.id,
            'team_id': n.team_id,
            'team_name': n.team.name if n.team else None,
            'subject': subject,
            'from': from_addr,
            'email': email,
            'html': html,
            'text': text,
            'meta': meta_payload,
        }

        request_kwargs: dict[str, Any]
        if method == 'GET':
            param_name = os.getenv('N8N_EMAIL_GET_PARAM', 'payload').strip() or 'payload'
            request_kwargs = {'params': {param_name: json.dumps(payload)}}
            request_fn = requests.get
        else:
            request_kwargs = {'json': payload}
            request_fn = requests.post

        try:
            r = request_fn(webhook_url, headers=headers, timeout=20, **request_kwargs)
            last_status_code = r.status_code
            last_response_text = (r.text[:5000] if isinstance(getattr(r, 'text', ''), str) else '')
            if 200 <= r.status_code < 300:
                delivered_count += 1
            else:
                failures.append({
                    'email': email,
                    'http_status': r.status_code,
                    'response_text': last_response_text,
                })
        except requests.RequestException as exc:
            last_status_code = getattr(getattr(exc, 'response', None), 'status_code', None)
            last_response_text = str(exc)[:5000]
            failures.append({
                'email': email,
                'error': str(exc),
                'http_status': last_status_code,
            })

    status = 'ok' if delivered_count == total_recipients else ('partial' if delivered_count else 'error')
    result: dict[str, Any] = {
        'status': status,
        'http_status': last_status_code,
        'recipient_count': total_recipients,
        'delivered_count': delivered_count,
        'webhook_url': webhook_url,
        'response_text': last_response_text,
    }
    if failures:
        result['failures'] = failures
    return result

@api_bp.route('/newsletters/<int:newsletter_id>/render.<fmt>', methods=['GET'])
@require_api_key
def render_newsletter(newsletter_id: int, fmt: str):
    try:
        n = Newsletter.query.get_or_404(newsletter_id)
        data = _load_newsletter_json(n) or {}
        team_logo = data.get('team_logo')
        if not team_logo and n.team and getattr(n.team, 'logo', None):
            team_logo = n.team.logo
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
            'team_logo': team_logo,
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
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500

@api_bp.route('/newsletters/<int:newsletter_id>/send', methods=['POST'])
@require_api_key
def send_newsletter(newsletter_id: int):
    """Send a newsletter via n8n webhook.
    Body options:
      - test_to: string or list of emails (optional). If provided, bypasses published check and does not mark as sent.
      - subject: override subject (optional)
      - webhook_url: override webhook URL (optional)
      - dry_run: bool, forward to webhook (optional)
    """
    try:
        n = Newsletter.query.get_or_404(newsletter_id)
        payload = request.get_json(silent=True) or {}
        test_to = payload.get('test_to')
        subject_override = payload.get('subject')
        webhook_override = payload.get('webhook_url')
        dry_run = bool(payload.get('dry_run'))

        recipients: list[str] | None = None
        is_test = False
        admin_preview = False
        if test_to:
            if isinstance(test_to, str):
                sentinel = test_to.strip().lower()
                if sentinel in {'__admins__', '__admin__', 'admins'}:
                    recipients = _admin_email_list()
                    if not recipients:
                        return jsonify({
                            'error': 'admin_emails_not_configured',
                            'message': 'Set ADMIN_EMAILS to a comma-separated list before sending admin previews.',
                        }), 400
                    admin_preview = True
                else:
                    recipients = [test_to]
                is_test = True
            elif isinstance(test_to, list):
                recipients = [str(x) for x in test_to if str(x).strip()]
                is_test = True
            else:
                return jsonify({'error': 'test_to must be string or list of strings'}), 400

        if not is_test:
            # Require published before full send
            if not n.published:
                return jsonify({'error': 'newsletter must be published/approved before sending'}), 400
            if n.email_sent:
                return jsonify({'error': 'newsletter already sent'}), 400

        if recipients is not None:
            deduped: list[str] = []
            seen: set[str] = set()
            for email in recipients:
                cleaned = (email or '').strip()
                key = cleaned.lower()
                if cleaned and key not in seen:
                    seen.add(key)
                    deduped.append(cleaned)
            recipients = deduped

        # Deliver
        out = _deliver_newsletter_via_webhook(
            n,
            recipients=recipients,  # None => fetch active subscribers
            subject_override=subject_override,
            webhook_url_override=webhook_override,
            dry_run=dry_run,
        )

        if admin_preview:
            try:
                _append_run_history({
                    'kind': 'newsletter-admin-test-send',
                    'newsletter_id': n.id,
                    'team_id': n.team_id,
                    'status': out.get('status'),
                    'http_status': out.get('http_status'),
                    'recipient_count': out.get('recipient_count'),
                    'delivered_count': out.get('delivered_count'),
                    'admin_recipients': recipients,
                    'dry_run': bool(dry_run),
                    'run_by': getattr(g, 'user_email', None),
                })
            except Exception:
                pass

        # Mark sent only for non-test ok runs
        if out.get('status') == 'ok' and not is_test:
            from datetime import datetime as _dt, timezone as _tz
            # Count recipients used
            if recipients is None:
                subs = UserSubscription.query.filter_by(team_id=n.team_id, active=True).all()
                valid_subs = [s for s in subs if (s.email or '').strip() and not s.email_bounced]
                used_count = len(valid_subs)
            else:
                used_count = len(recipients)
            n.email_sent = True
            n.email_sent_date = _dt.now(_tz.utc)
            n.subscriber_count = used_count
            # Update last_email_sent for subscriptions we attempted to deliver
            try:
                ts = n.email_sent_date
                if recipients is None:
                    for s in valid_subs:
                        s.last_email_sent = ts
                else:
                    # Update only those included in recipients list
                    recip_set = set(recipients)
                    subs_sel = UserSubscription.query.filter_by(team_id=n.team_id, active=True).all()
                    for s in subs_sel:
                        if (s.email or '').strip() in recip_set:
                            s.last_email_sent = ts
            except Exception:
                pass
            db.session.commit()
        response_payload = {'newsletter_id': n.id, **out}
        if admin_preview:
            response_payload['admin_preview'] = True
            response_payload['admin_recipients'] = recipients
        return jsonify(response_payload)
    except Exception as e:
        logger.exception('send_newsletter failed')
        try:
            db.session.rollback()
        except Exception:
            pass
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500


@api_bp.route('/newsletters/<int:newsletter_id>', methods=['DELETE'])
@require_api_key
def delete_newsletter(newsletter_id: int):
    try:
        newsletter = Newsletter.query.get_or_404(newsletter_id)

        try:
            NewsletterComment.query.filter_by(newsletter_id=newsletter.id).delete(synchronize_session=False)
        except Exception:
            db.session.rollback()
            raise

        db.session.delete(newsletter)
        db.session.commit()

        return jsonify({'status': 'deleted', 'newsletter_id': newsletter_id})
    except Exception as e:
        logger.exception('delete_newsletter failed')
        try:
            db.session.rollback()
        except Exception:
            pass
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500
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
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500

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
        try:
            out = generate_weekly_newsletter_with_mcp_sync(int(team_db_id), tdate)
        except NoActiveLoaneesError as e:
            return jsonify({
                'team_db_id': team_db_id,
                'ran_for': tdate.isoformat(),
                'status': 'skipped',
                'reason': 'no_active_loanees',
                'message': str(e),
            }), 200
        return jsonify({'team_db_id': team_db_id, 'ran_for': tdate.isoformat(), 'result': out})
    except Exception as e:
        logger.exception("generate-weekly-mcp-team failed")
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500

# --- Guest loan flag endpoints ---
from src.models.league import LoanFlag, AdminSetting

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
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500

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
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500

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
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500

# --- Admin config & run control ---

def _get_admin_bool(key: str, default: bool = False) -> bool:
    try:
        row = AdminSetting.query.filter_by(key=key).first()
        if row and row.value_json is not None:
            v = row.value_json.strip().lower()
            return v in ('1', 'true', 'yes', 'y')
    except Exception:
        pass
    return default

def _set_admin_values(kv: dict[str, str]):
    for k, v in kv.items():
        row = AdminSetting.query.filter_by(key=k).first()
        if not row:
            row = AdminSetting(key=k, value_json=str(v))
            db.session.add(row)
        else:
            row.value_json = str(v)
    db.session.commit()

@api_bp.route('/admin/config', methods=['GET'])
@require_api_key
def get_admin_config():
    try:
        rows = AdminSetting.query.all()
        return jsonify({r.key: r.value_json for r in rows})
    except Exception as e:
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500

@api_bp.route('/admin/config', methods=['POST'])
@require_api_key
def update_admin_config():
    try:
        payload = request.get_json() or {}
        settings = payload.get('settings') or {}
        if not isinstance(settings, dict):
            return jsonify({'error': 'settings must be an object'}), 400
        # store as stringified booleans/values
        to_store = {k: ('true' if bool(v) else 'false') if isinstance(v, bool) else str(v) for k, v in settings.items()}
        _set_admin_values(to_store)
        return jsonify({'message': 'Updated', 'updated': list(settings.keys())})
    except Exception as e:
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500

@api_bp.route('/admin/run-status', methods=['GET'])
@require_api_key
def get_run_status():
    try:
        paused = _get_admin_bool('runs_paused', False)
        return jsonify({'runs_paused': paused})
    except Exception as e:
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500

@api_bp.route('/admin/run-status', methods=['POST'])
@require_api_key
def set_run_status():
    try:
        payload = request.get_json() or {}
        paused = bool(payload.get('runs_paused', False))
        _set_admin_values({'runs_paused': 'true' if paused else 'false'})
        return jsonify({'message': 'Run status updated', 'runs_paused': paused})
    except Exception as e:
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500

# --- Admin: Loans management ---
@api_bp.route('/admin/loans', methods=['GET'])
@require_api_key
def admin_list_loans():
    try:
        primary_team_api_id = request.args.get('primary_team_api_id', type=int)
        primary_team_db_id = request.args.get('primary_team_db_id', type=int)
        season = request.args.get('season', type=int)
        active_only = request.args.get('active_only', 'true').lower() in ('true','1','yes','y')

        q = LoanedPlayer.query
        # Filter by primary team
        if primary_team_db_id:
            q = q.filter(LoanedPlayer.primary_team_id == primary_team_db_id)
        elif primary_team_api_id:
            # Resolve DB id from API id (requires season)
            if season is None:
                return jsonify({'error': 'season is required when filtering by primary_team_api_id'}), 400
            row = Team.query.filter_by(team_id=primary_team_api_id, season=season).first()
            if not row:
                return jsonify({'error': f'Primary team api_id={primary_team_api_id} not found for season {season}'}), 404
            q = q.filter(LoanedPlayer.primary_team_id == row.id)

        if active_only:
            q = q.filter(LoanedPlayer.is_active.is_(True))

        # Optional: basic search by player_id or name
        player_id = request.args.get('player_id', type=int)
        if player_id:
            q = q.filter(LoanedPlayer.player_id == player_id)
        player_name = request.args.get('player_name')
        if player_name:
            q = q.filter(LoanedPlayer.player_name.ilike(f"%{player_name}%"))

        loans = q.order_by(LoanedPlayer.updated_at.desc()).all()
        return jsonify([l.to_dict() for l in loans])
    except Exception as e:
        logger.exception('admin_list_loans failed')
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500

def _ensure_team_admin(api_team_id: int, season_start_year: int) -> Team | None:
    """
    Ensure a Team row exists for the given API team id and season.

    Improvement: attach the correct League (Top‑5) for the season when creating
    a new Team, so the admin UI can group teams by league instead of "Other".
    """
    try:
        if not api_team_id:
            return None

        # 1) Existing row for this season?
        t = Team.query.filter_by(team_id=api_team_id, season=season_start_year).first()
        if t:
            return t

        # 2) Fetch minimal team info for naming
        tdata = api_client.get_team_by_id(api_team_id, season_start_year)
        ti = (tdata or {}).get('team') or {}
        team_name = ti.get('name') or f'Team {api_team_id}'
        team_code = ti.get('code')
        team_country = ti.get('country') or 'Unknown'
        founded = ti.get('founded')
        national = bool(ti.get('national', False))
        logo = ti.get('logo')

        # 3) Try to resolve league from Top‑5 mapping for this season
        league_fk_id = None
        try:
            teams_map = api_client.get_teams_with_leagues_for_season(season_start_year)  # {api_team_id: {...}}
            meta = teams_map.get(api_team_id)
            if meta:
                league_api_id = meta.get('league_id')
                league_name = meta.get('league_name')
                league_country = meta.get('country') or 'Unknown'
                if league_api_id and league_name:
                    league_row = League.query.filter_by(league_id=league_api_id).first()
                    if not league_row:
                        league_row = League(
                            league_id=league_api_id,
                            name=league_name,
                            country=league_country,
                            season=season_start_year,
                            is_european_top_league=True,
                        )
                        db.session.add(league_row)
                        db.session.flush()
                    league_fk_id = league_row.id
        except Exception:
            # Non‑fatal; leave as None if we cannot resolve
            pass

        # 4) Create team row with resolved league (if found)
        team = Team(
            team_id=api_team_id,
            name=team_name,
            code=team_code,
            country=team_country,
            founded=founded,
            national=national,
            logo=logo,
            season=season_start_year or api_client.current_season_start_year,
            is_active=True,
            league_id=league_fk_id,
        )
        db.session.add(team)
        db.session.flush()
        return team
    except Exception:
        return None

@api_bp.route('/admin/loans', methods=['POST'])
@require_api_key
def admin_create_loan():
    try:
        data = request.get_json() or {}
        player_id = int(data.get('player_id') or 0)
        if not player_id:
            return jsonify({'error': 'player_id is required'}), 400
        player_name = (data.get('player_name') or '').strip() or f'Player {player_id}'
        season = data.get('season')
        window_key = (data.get('window_key') or '').strip() or None
        if season is None and window_key:
            try:
                season = int(window_key.split('::')[0].split('-')[0])
            except Exception:
                season = None
        season = int(season) if season is not None else api_client.current_season_start_year

        # Resolve or create teams from API ids
        pt_api = data.get('primary_team_api_id')
        lt_api = data.get('loan_team_api_id')
        pt_db = data.get('primary_team_db_id')
        lt_db = data.get('loan_team_db_id')
        if not (pt_db or pt_api) or not (lt_db or lt_api):
            return jsonify({'error': 'primary_team_* and loan_team_* are required (db_id or api_id)'}), 400

        parent_team = Team.query.get(int(pt_db)) if pt_db else _ensure_team_admin(int(pt_api), season)
        loan_team = Team.query.get(int(lt_db)) if lt_db else _ensure_team_admin(int(lt_api), season)
        if not parent_team or not loan_team:
            return jsonify({'error': 'Unable to resolve teams. Provide valid db ids or api ids with season.'}), 400

        # Names fallback
        primary_team_name = (data.get('primary_team_name') or parent_team.name)
        loan_team_name = (data.get('loan_team_name') or loan_team.name)
        reviewer_notes = (data.get('reviewer_notes') or '').strip() or None

        # Enforce uniqueness by key; reactivate if an inactive row exists
        any_row = LoanedPlayer.query.filter_by(
            player_id=player_id,
            primary_team_id=parent_team.id,
            loan_team_id=loan_team.id,
            window_key=window_key,
        ).first()
        if any_row:
            if any_row.is_active:
                return jsonify({'error': 'duplicate loan for same player/teams/window'}), 409
            # Reactivate existing record
            any_row.is_active = True
            any_row.player_name = player_name or any_row.player_name
            any_row.primary_team_name = primary_team_name or any_row.primary_team_name
            any_row.loan_team_name = loan_team_name or any_row.loan_team_name
            any_row.reviewer_notes = reviewer_notes or any_row.reviewer_notes
            db.session.commit()
            return jsonify({'message': 'reactivated', 'loan': any_row.to_dict()}), 200

        loan = LoanedPlayer(
            player_id=player_id,
            player_name=player_name,
            primary_team_id=parent_team.id,
            primary_team_name=primary_team_name,
            loan_team_id=loan_team.id,
            loan_team_name=loan_team_name,
            window_key=window_key,
            reviewer_notes=reviewer_notes,
            is_active=True,
        )
        db.session.add(loan)
        db.session.commit()
        return jsonify({'message': 'created', 'loan': loan.to_dict()}), 201
    except Exception as e:
        logger.exception('admin_create_loan failed')
        db.session.rollback()
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500

@api_bp.route('/admin/loans/<int:loan_id>', methods=['PUT'])
@require_api_key
def admin_update_loan(loan_id: int):
    try:
        loan = LoanedPlayer.query.get_or_404(loan_id)
        data = request.get_json() or {}

        # Move between teams if provided
        season = data.get('season')
        if season is not None:
            try:
                season = int(season)
            except Exception:
                season = api_client.current_season_start_year
        else:
            season = api_client.current_season_start_year

        def _maybe_move_team(kind: str):
            api_id = data.get(f'{kind}_team_api_id')
            db_id = data.get(f'{kind}_team_db_id')
            name = data.get(f'{kind}_team_name')
            if db_id or api_id:
                team = Team.query.get(int(db_id)) if db_id else _ensure_team_admin(int(api_id), season)
                if not team:
                    raise ValueError(f"Unable to resolve {kind} team")
                if kind == 'primary':
                    new_primary_id = team.id
                    new_loan_id = loan.loan_team_id
                else:
                    new_primary_id = loan.primary_team_id
                    new_loan_id = team.id
                # Pre-check for uniqueness conflict against another row
                exists = LoanedPlayer.query.filter(
                    LoanedPlayer.id != loan.id,
                    LoanedPlayer.player_id == loan.player_id,
                    LoanedPlayer.primary_team_id == new_primary_id,
                    LoanedPlayer.loan_team_id == new_loan_id,
                    LoanedPlayer.window_key == loan.window_key,
                ).first()
                if exists:
                    raise ValueError('update would duplicate an existing loan row')
                if kind == 'primary':
                    loan.primary_team_id = new_primary_id
                    if name:
                        loan.primary_team_name = name
                else:
                    loan.loan_team_id = new_loan_id
                    if name:
                        loan.loan_team_name = name
            elif name:
                if kind == 'primary':
                    loan.primary_team_name = name
                else:
                    loan.loan_team_name = name

        _maybe_move_team('primary')
        _maybe_move_team('loan')

        if 'is_active' in data:
            loan.is_active = bool(data.get('is_active'))
        if 'player_name' in data:
            loan.player_name = (data.get('player_name') or '').strip() or loan.player_name
        if 'window_key' in data:
            loan.window_key = (data.get('window_key') or '').strip() or None
        if 'reviewer_notes' in data:
            loan.reviewer_notes = (data.get('reviewer_notes') or '').strip() or None

        db.session.commit()
        return jsonify({'message': 'updated', 'loan': loan.to_dict()})
    except Exception as e:
        logger.exception('admin_update_loan failed')
        db.session.rollback()
        # Uniqueness conflict should return 409
        msg = str(e)
        if 'duplicate' in msg or 'unique' in msg or 'would duplicate' in msg:
            return jsonify({'error': msg}), 409
        return jsonify({'error': msg}), 500

@api_bp.route('/admin/loans/cleanup-duplicates', methods=['POST'])
@require_api_key
def admin_cleanup_duplicate_loans():
    """
    Remove duplicate LoanedPlayer rows sharing (player_id, primary_team_id, loan_team_id, window_key).
    Optional JSON body: { "season": 2025 } to limit by season.
    Keeps the most recently updated row (prefer active), deletes the rest.
    """
    try:
        payload = request.get_json(silent=True) or {}
        season = payload.get('season')
        deleted = 0
        groups = {}
        q = LoanedPlayer.query
        if season:
            slug = f"{int(season)}-{str(int(season) + 1)[-2:]}"
            q = q.filter(LoanedPlayer.window_key.like(f"{slug}%"))
        rows = q.all()
        for r in rows:
            key = (r.player_id, r.primary_team_id, r.loan_team_id, r.window_key)
            groups.setdefault(key, []).append(r)
        for key, lst in groups.items():
            if len(lst) <= 1:
                continue
            # Pick canonical row: active first, then newest updated_at
            lst_sorted = sorted(lst, key=lambda x: ((1 if x.is_active else 0), (x.updated_at or x.created_at)), reverse=True)
            keep = lst_sorted[0]
            to_delete = [r for r in lst_sorted[1:]]
            for r in to_delete:
                try:
                    db.session.delete(r)
                    deleted += 1
                except Exception:
                    db.session.rollback()
                    continue
        if deleted:
            db.session.commit()
        try:
            _append_run_history({'kind': 'cleanup-duplicates', 'season': season, 'deleted': deleted})
        except Exception:
            pass
        return jsonify({'deleted': deleted, 'season': season}), 200
    except Exception as e:
        logger.exception('admin_cleanup_duplicate_loans failed')
        db.session.rollback()
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500

@api_bp.route('/admin/loans/<int:loan_id>/deactivate', methods=['POST'])
@require_api_key
def admin_deactivate_loan(loan_id: int):
    try:
        loan = LoanedPlayer.query.get_or_404(loan_id)
        loan.is_active = False
        db.session.commit()
        return jsonify({'message': 'deactivated', 'loan': loan.to_dict()})
    except Exception as e:
        logger.exception('admin_deactivate_loan failed')
        db.session.rollback()
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500

@api_bp.route('/admin/loans/seed-top5', methods=['POST'])
@require_api_key
def admin_seed_top5_loans():
    """Seed LoanedPlayer rows for Top-5 European leagues for a given season.

    Body: { season: int, window_key?: str, league_ids?: [int], dry_run?: bool }
    - season: starting year (e.g., 2025 for 2025-26)
    - window_key default: "{season}-{(season+1)%100:02d}::FULL"
    - league_ids default: [39, 140, 78, 135, 61]
    """
    try:
        data = request.get_json() or {}
        season = int(data.get('season') or 0)
        if not season:
            return jsonify({'error': 'season is required'}), 400
        league_ids = data.get('league_ids') or [39, 140, 78, 135, 61]
        dry_run = bool(data.get('dry_run'))
        overwrite = bool(data.get('overwrite'))

        requester = getattr(g, 'user_email', None)
        client_ip = get_client_ip()
        logger.info(
            'Admin seed-top5 request season=%s dry_run=%s overwrite=%s leagues=%s user=%s ip=%s',
            season,
            dry_run,
            overwrite,
            league_ids,
            requester,
            client_ip,
        )

        # Compute default window_key (e.g., 2025-26::FULL)
        window_key = (data.get('window_key') or '').strip()
        if not window_key:
            end_two = str((season + 1) % 100).zfill(2)
            window_key = f"{season}-{end_two}::FULL"

        # Ensure season data in local DB
        _sync_season(season=season)
        api_client.set_season_year(season)
        api_client._prime_team_cache(season)

        created = 0
        skipped = 0
        candidates_total = 0
        details = []

        # Collect candidates from two sources: direct transfers and multi-team detection
        direct = api_client.get_direct_loan_candidates(window_key, league_ids, season=season) or {}
        multi_team = api_client.detect_multi_team_players(league_ids, window_key, season=season) or {}

        # Merge keys
        player_ids = set(direct.keys()) | set(multi_team.keys())
        candidates_total = len(player_ids)

        # Track candidate triplets to support overwrite/prune
        candidate_triplets: set[tuple[int,int,int]] = set()

        for player_id in player_ids:
            try:
                # Derive teams
                d = direct.get(player_id) or {}
                mt = multi_team.get(player_id) or []
                # multi_team format often [loan_team_id, primary_team_id]
                loan_team_api_id = d.get('loan_team_id') or (mt[0] if len(mt) > 0 else None)
                primary_team_api_id = d.get('primary_team_id') or (mt[1] if len(mt) > 1 else None)
                if not (loan_team_api_id and primary_team_api_id):
                    skipped += 1
                    details.append({'player_id': player_id, 'status': 'skip_missing_teams'})
                    continue

                # Fetch player info (name)
                info = api_client.get_player_by_id(player_id) or {}
                player_info = info.get('player') or {}
                player_name = (player_info.get('name') or f'Player {player_id}')

                # Resolve Team DB rows (create if needed)
                parent_team = _ensure_team_admin(int(primary_team_api_id), season)
                loan_team = _ensure_team_admin(int(loan_team_api_id), season)
                if not parent_team or not loan_team:
                    skipped += 1
                    details.append({'player_id': player_id, 'status': 'skip_unresolved_team'})
                    continue

                # Record candidate triplet for potential pruning
                candidate_triplets.add((int(player_id), int(parent_team.id), int(loan_team.id)))

                # Duplicate handling: prefer reactivation over new row
                any_row = LoanedPlayer.query.filter_by(
                    player_id=int(player_id),
                    primary_team_id=parent_team.id,
                    loan_team_id=loan_team.id,
                    window_key=window_key,
                ).first()
                if any_row:
                    if any_row.is_active:
                        skipped += 1
                        details.append({'player_id': player_id, 'status': 'skip_duplicate_active'})
                        continue
                    if dry_run:
                        details.append({'player_id': player_id, 'status': 'would_reactivate'})
                        continue
                    any_row.is_active = True
                    any_row.player_name = player_name or any_row.player_name
                    any_row.primary_team_name = parent_team.name
                    any_row.loan_team_name = loan_team.name
                    details.append({'player_id': player_id, 'status': 'reactivated'})
                else:
                    if dry_run:
                        details.append({'player_id': player_id, 'status': 'dry_run'})
                        continue
                    loan = LoanedPlayer(
                        player_id=int(player_id),
                        player_name=player_name,
                        primary_team_id=parent_team.id,
                        primary_team_name=parent_team.name,
                        loan_team_id=loan_team.id,
                        loan_team_name=loan_team.name,
                        window_key=window_key,
                        reviewer_notes='Seeded via /admin/loans/seed-top5',
                        is_active=True,
                    )
                    db.session.add(loan)
                    created += 1
                    details.append({'player_id': player_id, 'status': 'created'})
            except Exception as ex:
                skipped += 1
                details.append({'player_id': player_id, 'status': f'error: {ex}'})

        if not dry_run:
            db.session.commit()

        # Optional pruning of stale seeded loans for this season
        pruned = 0
        if overwrite and not dry_run:
            try:
                # Deactivate active rows seeded via seed-top5 for same season not present in new candidates
                existing_rows = LoanedPlayer.query.filter(
                    LoanedPlayer.is_active.is_(True)
                ).all()
                for row in existing_rows:
                    try:
                        if not row.window_key or not str(row.window_key).startswith(str(season)):
                            continue
                        # Only prune rows created by top5 seeding to avoid touching hand-entered or team‑seeded items
                        if not row.reviewer_notes or 'seed-top5' not in row.reviewer_notes:
                            continue
                        triplet = (int(row.player_id), int(row.primary_team_id), int(row.loan_team_id))
                        if triplet not in candidate_triplets:
                            row.is_active = False
                            pruned += 1
                    except Exception:
                        continue
                if pruned:
                    db.session.commit()
            except Exception:
                db.session.rollback()

        # Ensure teams for this season have leagues assigned (idempotent backfill)
        if not dry_run:
            try:
                team_map = api_client.get_teams_with_leagues_for_season(season) or {}
                existing_league_fk_by_api_id: dict[int, int] = {}
                for row in Team.query.filter(Team.league_id.isnot(None)).all():
                    existing_league_fk_by_api_id[row.team_id] = row.league_id
                updated = 0
                created_leagues = 0
                for t in Team.query.filter_by(season=season).filter(Team.league_id.is_(None)).all():
                    meta = team_map.get(t.team_id)
                    league_row = None
                    if meta:
                        league_api_id = meta.get('league_id')
                        league_name = meta.get('league_name')
                        league_country = meta.get('country') or 'Unknown'
                        if league_api_id and league_name:
                            league_row = League.query.filter_by(league_id=league_api_id).first()
                            if not league_row:
                                league_row = League(
                                    league_id=league_api_id,
                                    name=league_name,
                                    country=league_country,
                                    season=season,
                                    is_european_top_league=True,
                                )
                                db.session.add(league_row)
                                db.session.flush()
                                created_leagues += 1
                    if league_row is None:
                        fk = existing_league_fk_by_api_id.get(t.team_id)
                        if fk:
                            t.league_id = fk
                            updated += 1
                            continue
                    if league_row is None:
                        continue
                    t.league_id = league_row.id
                    updated += 1
                if updated or created_leagues:
                    db.session.commit()
            except Exception:
                db.session.rollback()
                pass

        try:
            _append_run_history({
                'kind': 'seed-top5-dry' if dry_run else 'seed-top5',
                'season': season,
                'window_key': window_key,
                'created': created,
                'skipped': skipped,
                'candidates': candidates_total,
                'dry_run': dry_run,
                'pruned': pruned if overwrite and not dry_run else 0,
            })
        except Exception:
            pass

        summary_payload = {
            'message': 'seed_complete' if not dry_run else 'dry_run_complete',
            'season': season,
            'window_key': window_key,
            'candidates': candidates_total,
            'created': created,
            'skipped': skipped,
            'pruned': pruned if overwrite and not dry_run else 0,
            'dry_run': dry_run,
            'details': details[:200],  # return a sample to limit payload
        }
        logger.info(
            'Admin seed-top5 completed season=%s dry_run=%s overwrite=%s created=%s skipped=%s pruned=%s',
            season,
            dry_run,
            overwrite,
            summary_payload['created'],
            summary_payload['skipped'],
            summary_payload['pruned'],
        )
        return jsonify(summary_payload)
    except Exception as e:
        logger.exception('admin_seed_top5_loans failed')
        try:
            db.session.rollback()
        except Exception:
            logger.warning('db.session.rollback failed during admin_seed_top5_loans error handling')
        return jsonify(_safe_error_payload(e, 'Failed to seed top five leagues. Please try again later.', include_detail=True)), 500

@api_bp.route('/admin/loans/seed-team', methods=['POST'])
@require_api_key
def admin_seed_team_loans():
    """Seed LoanedPlayer rows for a single parent (primary) team for a given season.

    Body: { season: int, team_db_id?: int, api_team_id?: int, window_key?: str, dry_run?: bool, overwrite?: bool }
    - season: starting year (e.g., 2025 for 2025-26)
    - Provide either team_db_id or api_team_id (API-Football id)
    - overwrite: if true, deactivates existing active loans for this player/primary team in the same season before creating new
    """
    try:
        data = request.get_json() or {}
        season = int(data.get('season') or 0)
        if not season:
            return jsonify({'error': 'season is required'}), 400
        team_db_id = data.get('team_db_id')
        api_team_id = data.get('api_team_id')
        dry_run = bool(data.get('dry_run'))
        overwrite = bool(data.get('overwrite'))

        if not (team_db_id or api_team_id):
            return jsonify({'error': 'team_db_id or api_team_id required'}), 400

        # Resolve parent team and api id
        parent_row = Team.query.get(int(team_db_id)) if team_db_id else _ensure_team_admin(int(api_team_id), season)
        if not parent_row:
            return jsonify({'error': 'Unable to resolve parent team'}), 400
        parent_api_id = int(parent_row.team_id)

        # Compute window_key if not provided
        window_key = (data.get('window_key') or '').strip()
        if not window_key:
            end_two = str((season + 1) % 100).zfill(2)
            window_key = f"{season}-{end_two}::FULL"

        _sync_season(season=season)
        api_client.set_season_year(season)
        api_client._prime_team_cache(season)

        # Default to Top-5 leagues; results will be filtered to parent_api_id
        league_ids = data.get('league_ids') or [39, 140, 78, 135, 61]

        direct = api_client.get_direct_loan_candidates(window_key, league_ids, season=season) or {}
        multi_team = api_client.detect_multi_team_players(league_ids, window_key, season=season) or {}

        # Filter to this parent team
        filtered_direct = {pid: info for pid, info in direct.items() if info.get('primary_team_id') == parent_api_id}
        filtered_multi = {pid: tids for pid, tids in multi_team.items() if (tids + [None, None])[1] == parent_api_id}

        player_ids = set(filtered_direct.keys()) | set(filtered_multi.keys())

        created = 0
        skipped = 0
        details = []

        for player_id in player_ids:
            try:
                d = filtered_direct.get(player_id) or {}
                mt = filtered_multi.get(player_id) or []
                loan_team_api_id = d.get('loan_team_id') or (mt[0] if len(mt) > 0 else None)
                primary_team_api_id = d.get('primary_team_id') or parent_api_id
                if not (loan_team_api_id and primary_team_api_id):
                    skipped += 1
                    details.append({'player_id': player_id, 'status': 'skip_missing_teams'})
                    continue

                info = api_client.get_player_by_id(player_id) or {}
                player_info = info.get('player') or {}
                player_name = (player_info.get('name') or f'Player {player_id}')

                parent_team = _ensure_team_admin(int(primary_team_api_id), season)
                loan_team = _ensure_team_admin(int(loan_team_api_id), season)
                if not parent_team or not loan_team:
                    skipped += 1
                    details.append({'player_id': player_id, 'status': 'skip_unresolved_team'})
                    continue

                if overwrite and not dry_run:
                    # Deactivate any existing active loans for this player at this parent in this season
                    season_start = season
                    # window_key season match by prefix
                    existing_rows = LoanedPlayer.query.filter(
                        LoanedPlayer.player_id == int(player_id),
                        LoanedPlayer.primary_team_id == parent_team.id,
                        LoanedPlayer.is_active.is_(True),
                    ).all()
                    for row in existing_rows:
                        try:
                            # Deactivate only same-season rows if window_key matches season
                            if row.window_key and str(row.window_key).startswith(str(season_start)):
                                row.is_active = False
                        except Exception:
                            continue

                # Duplicate handling: reuse/reactivate instead of creating duplicates
                any_row = LoanedPlayer.query.filter_by(
                    player_id=int(player_id),
                    primary_team_id=parent_team.id,
                    loan_team_id=loan_team.id,
                    window_key=window_key,
                ).first()
                if any_row:
                    if any_row.is_active:
                        skipped += 1
                        details.append({'player_id': player_id, 'status': 'skip_duplicate_active'})
                        continue
                    if dry_run:
                        details.append({'player_id': player_id, 'status': 'would_reactivate'})
                        continue
                    any_row.is_active = True
                    any_row.player_name = player_name or any_row.player_name
                    any_row.primary_team_name = parent_team.name
                    any_row.loan_team_name = loan_team.name
                    details.append({'player_id': player_id, 'status': 'reactivated'})
                else:
                    if dry_run:
                        details.append({'player_id': player_id, 'status': 'dry_run'})
                        continue
                    loan = LoanedPlayer(
                        player_id=int(player_id),
                        player_name=player_name,
                        primary_team_id=parent_team.id,
                        primary_team_name=parent_team.name,
                        loan_team_id=loan_team.id,
                        loan_team_name=loan_team.name,
                        window_key=window_key,
                        reviewer_notes='Seeded via /admin/loans/seed-team',
                        is_active=True,
                    )
                    db.session.add(loan)
                    created += 1
                    details.append({'player_id': player_id, 'status': 'created'})
            except Exception as ex:
                skipped += 1
                details.append({'player_id': player_id, 'status': f'error: {ex}'})

        if not dry_run:
            db.session.commit()

        try:
            _append_run_history({
                'kind': 'seed-team',
                'season': season,
                'team_db_id': parent_row.id,
                'api_team_id': parent_api_id,
                'created': created,
                'skipped': skipped,
                'dry_run': dry_run,
            })
        except Exception:
            pass

        return jsonify({
            'message': 'seed_team_complete' if not dry_run else 'seed_team_dry_run_complete',
            'season': season,
            'team_db_id': parent_row.id,
            'api_team_id': parent_api_id,
            'created': created,
            'skipped': skipped,
            'details': details[:200],
            'dry_run': dry_run,
        })
    except Exception as e:
        logger.exception('admin_seed_team_loans failed')
        db.session.rollback()
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500

# --- Admin: Missing names helpers ---
def _is_placeholder_name(name: str | None) -> bool:
    if not name:
        return True
    s = str(name).strip()
    if not s:
        return True
    low = s.lower()
    return low.startswith('player ') or low.startswith('unknown')

@api_bp.route('/admin/loans/missing-names', methods=['GET'])
@require_api_key
def admin_list_missing_player_names():
    """List loans whose player_name looks like a placeholder.

    Query params:
      - season: int (filters by window_key prefix)
      - primary_team_api_id: int (requires season)
      - primary_team_db_id: int
      - active_only: bool (default true)
      - limit: int (default 200)
    """
    try:
        season = request.args.get('season', type=int)
        primary_team_api_id = request.args.get('primary_team_api_id', type=int)
        primary_team_db_id = request.args.get('primary_team_db_id', type=int)
        active_only = request.args.get('active_only', 'true').lower() in ('true','1','yes','y')
        limit = request.args.get('limit', type=int) or 200

        q = LoanedPlayer.query
        if season is not None:
            slug = f"{season}-{str(season + 1)[-2:]}"
            q = q.filter(LoanedPlayer.window_key.like(f"{slug}%"))

        if primary_team_db_id:
            q = q.filter(LoanedPlayer.primary_team_id == int(primary_team_db_id))
        elif primary_team_api_id:
            if season is None:
                return jsonify({'error': 'season is required when using primary_team_api_id'}), 400
            row = Team.query.filter_by(team_id=primary_team_api_id, season=season).first()
            if not row:
                return jsonify({'error': f'Primary team api_id={primary_team_api_id} not found for season {season}'}), 404
            q = q.filter(LoanedPlayer.primary_team_id == row.id)

        if active_only:
            q = q.filter(LoanedPlayer.is_active.is_(True))

        # DB-side placeholder filter
        q = q.filter(
            or_(
                LoanedPlayer.player_name.is_(None),
                LoanedPlayer.player_name == '',
                LoanedPlayer.player_name.ilike('Player %'),
                LoanedPlayer.player_name.ilike('Unknown%'),
            )
        ).order_by(LoanedPlayer.updated_at.desc()).limit(limit)

        rows = q.all()
        return jsonify([r.to_dict() for r in rows])
    except Exception as e:
        logger.exception('admin_list_missing_player_names failed')
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500

@api_bp.route('/admin/loans/backfill-names', methods=['POST'])
@require_api_key
def admin_backfill_player_names():
    """Backfill player_name for placeholder rows using API-Football fallbacks.

    Body JSON options:
      - season: int (required to resolve primary_team_api_id)
      - primary_team_api_id: int (optional)
      - primary_team_db_id: int (optional)
      - active_only: bool (default true)
      - limit: int (default 200)
      - dry_run: bool (default false)
    """
    try:
        data = request.get_json() or {}
        season = data.get('season')
        season = int(season) if season is not None else api_client.current_season_start_year
        primary_team_api_id = data.get('primary_team_api_id')
        primary_team_db_id = data.get('primary_team_db_id')
        active_only = bool(data.get('active_only', True))
        limit = int(data.get('limit') or 200)
        dry_run = bool(data.get('dry_run'))

        q = LoanedPlayer.query
        if season is not None:
            slug = f"{season}-{str(season + 1)[-2:]}"
            q = q.filter(LoanedPlayer.window_key.like(f"{slug}%"))

        if primary_team_db_id:
            q = q.filter(LoanedPlayer.primary_team_id == int(primary_team_db_id))
        elif primary_team_api_id:
            row = Team.query.filter_by(team_id=int(primary_team_api_id), season=season).first()
            if not row:
                return jsonify({'error': f'Primary team api_id={primary_team_api_id} not found for season {season}'}), 404
            q = q.filter(LoanedPlayer.primary_team_id == row.id)

        if active_only:
            q = q.filter(LoanedPlayer.is_active.is_(True))

        q = q.filter(
            or_(
                LoanedPlayer.player_name.is_(None),
                LoanedPlayer.player_name == '',
                LoanedPlayer.player_name.ilike('Player %'),
                LoanedPlayer.player_name.ilike('Unknown%'),
            )
        ).order_by(LoanedPlayer.updated_at.desc()).limit(limit)

        rows = q.all()

        updated, skipped = 0, 0
        details = []

        # Make sure API client season aligns for lookups
        try:
            api_client.set_season_year(season)
        except Exception:
            pass

        for r in rows:
            try:
                info = api_client.get_player_by_id(int(r.player_id), season=season) or {}
                p = (info.get('player') or {}) if isinstance(info, dict) else {}
                name = p.get('name') or (f"{p.get('firstname','').strip()} {p.get('lastname','').strip()}".strip())
                if not name or _is_placeholder_name(name):
                    skipped += 1
                    details.append({'loan_id': r.id, 'player_id': r.player_id, 'status': 'no_name_found'})
                    continue
                if dry_run:
                    updated += 1
                    details.append({'loan_id': r.id, 'player_id': r.player_id, 'new_name': name, 'status': 'would_update'})
                else:
                    r.player_name = name
                    updated += 1
                    details.append({'loan_id': r.id, 'player_id': r.player_id, 'new_name': name, 'status': 'updated'})
            except Exception as ex:
                skipped += 1
                details.append({'loan_id': r.id, 'player_id': r.player_id, 'status': f'error: {ex}'})

        if not dry_run and updated:
            db.session.commit()

        try:
            _append_run_history({
                'kind': 'backfill-player-names',
                'season': season,
                'team_api_id': int(primary_team_api_id) if primary_team_api_id else None,
                'updated': updated,
                'skipped': skipped,
                'dry_run': dry_run,
            })
        except Exception:
            pass

        return jsonify({
            'season': season,
            'updated': updated,
            'skipped': skipped,
            'dry_run': dry_run,
            'processed': len(rows),
            'details': details[:200]
        })
    except Exception as e:
        logger.exception('admin_backfill_player_names failed')
        db.session.rollback()
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500

@api_bp.route('/admin/backfill-team-leagues/<int:season>', methods=['POST'])
@require_api_key
def admin_backfill_team_leagues(season: int):
    """
    Backfill missing Team.league_id for a given season using API‑Football Top‑5
    league mapping. Helpful if teams were created via admin seeding before
    syncing leagues/teams for that season.
    """
    try:
        if not season:
            return jsonify({'error': 'season is required'}), 400

        # Map: API team id -> { name, league_name, league_id, country }
        team_map = api_client.get_teams_with_leagues_for_season(season) or {}

        # Build an internal fallback mapping from existing rows (any season)
        # api_team_id -> existing league FK id
        existing_league_fk_by_api_id: dict[int, int] = {}
        for row in Team.query.filter(Team.league_id.isnot(None)).all():
            existing_league_fk_by_api_id[row.team_id] = row.league_id

        updated = 0
        created_leagues = 0
        examined = 0

        rows = Team.query.filter_by(season=season).all()
        for t in rows:
            examined += 1
            if t.league_id:
                continue
            meta = team_map.get(t.team_id)
            league_row = None
            if meta:
                league_api_id = meta.get('league_id')
                league_name = meta.get('league_name')
                league_country = meta.get('country') or 'Unknown'
                if league_api_id and league_name:
                    league_row = League.query.filter_by(league_id=league_api_id).first()
                    if not league_row:
                        league_row = League(
                            league_id=league_api_id,
                            name=league_name,
                            country=league_country,
                            season=season,
                            is_european_top_league=True,
                        )
                        db.session.add(league_row)
                        db.session.flush()
                        created_leagues += 1
            # Fallback: copy league FK from any season if we have one
            if league_row is None:
                fallback_fk = existing_league_fk_by_api_id.get(t.team_id)
                if fallback_fk:
                    t.league_id = fallback_fk
                    updated += 1
                    continue
            if league_row is None:
                continue
            t.league_id = league_row.id
            updated += 1

        db.session.commit()
        try:
            _append_run_history({
                'kind': 'backfill-team-leagues',
                'season': season,
                'updated': updated,
                'created_leagues': created_leagues,
                'message': f'Backfilled leagues for season {season}: updated {updated}, created {created_leagues}'
            })
        except Exception:
            pass
        return jsonify({
            'season': season,
            'examined': examined,
            'updated_teams': updated,
            'created_leagues': created_leagues,
        })
    except Exception as e:
        logger.exception('admin_backfill_team_leagues failed')
        db.session.rollback()
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500

@api_bp.route('/admin/backfill-team-leagues', methods=['POST'])
@require_api_key
def admin_backfill_team_leagues_all():
    """
    Backfill Team.league_id across multiple seasons.

    Body (optional): { "seasons": [2023, 2024, ...] }
    If not provided, operates on all distinct Team.season values present.
    """
    try:
        payload = request.get_json() or {}
        seasons = payload.get('seasons')
        if not seasons:
            seasons = [row[0] for row in db.session.query(Team.season).distinct().all()]

        summary = []
        total_updated = 0
        total_created_leagues = 0
        total_examined = 0

        for season in seasons:
            try:
                season = int(season)
                team_map = api_client.get_teams_with_leagues_for_season(season) or {}
                # Build fallback from existing rows (any season)
                existing_league_fk_by_api_id: dict[int, int] = {}
                for row in Team.query.filter(Team.league_id.isnot(None)).all():
                    existing_league_fk_by_api_id[row.team_id] = row.league_id
                updated = 0
                created_leagues = 0
                examined = 0
                rows = Team.query.filter_by(season=season).all()
                for t in rows:
                    examined += 1
                    if t.league_id:
                        continue
                    meta = team_map.get(t.team_id)
                    league_row = None
                    if meta:
                        league_api_id = meta.get('league_id')
                        league_name = meta.get('league_name')
                        league_country = meta.get('country') or 'Unknown'
                        if league_api_id and league_name:
                            league_row = League.query.filter_by(league_id=league_api_id).first()
                            if not league_row:
                                league_row = League(
                                    league_id=league_api_id,
                                    name=league_name,
                                    country=league_country,
                                    season=season,
                                    is_european_top_league=True,
                                )
                                db.session.add(league_row)
                                db.session.flush()
                                created_leagues += 1
                    # Fallback: copy league FK from any season
                    if league_row is None:
                        fallback_fk = existing_league_fk_by_api_id.get(t.team_id)
                        if fallback_fk:
                            t.league_id = fallback_fk
                            updated += 1
                            continue
                    if league_row is None:
                        continue
                    t.league_id = league_row.id
                    updated += 1
                db.session.commit()
                summary.append({
                    'season': season,
                    'examined': examined,
                    'updated_teams': updated,
                    'created_leagues': created_leagues,
                })
                total_updated += updated
                total_created_leagues += created_leagues
                total_examined += examined
            except Exception:
                db.session.rollback()
                summary.append({'season': int(season), 'error': 'failed'})

        try:
            _append_run_history({
                'kind': 'backfill-team-leagues-all',
                'seasons': seasons,
                'updated': total_updated,
                'created_leagues': total_created_leagues,
                'message': f'Backfilled all seasons ({len(seasons)}): updated {total_updated}, created leagues {total_created_leagues}'
            })
        except Exception:
            pass
        return jsonify({
            'summary': summary,
            'totals': {
                'seasons': len(seasons),
                'examined': total_examined,
                'updated_teams': total_updated,
                'created_leagues': total_created_leagues,
            }
        })
    except Exception as e:
        logger.exception('admin_backfill_team_leagues_all failed')
        db.session.rollback()
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500

# --- Admin: Flags management (list/update) ---
@api_bp.route('/admin/flags', methods=['GET'])
@require_api_key
def admin_list_flags():
    try:
        status = (request.args.get('status') or 'all').strip().lower()
        q = LoanFlag.query
        if status in ('pending', 'resolved'):
            q = q.filter(LoanFlag.status == status)
        rows = q.order_by(LoanFlag.created_at.desc()).all()
        return jsonify([{
            'id': r.id,
            'player_api_id': r.player_api_id,
            'primary_team_api_id': r.primary_team_api_id,
            'loan_team_api_id': r.loan_team_api_id,
            'season': r.season,
            'reason': r.reason,
            'email': r.email,
            'status': r.status,
            'admin_note': r.admin_note,
            'created_at': r.created_at.isoformat() if r.created_at else None,
            'resolved_at': r.resolved_at.isoformat() if r.resolved_at else None,
        } for r in rows])
    except Exception as e:
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500

@api_bp.route('/admin/flags/<int:flag_id>', methods=['POST'])
@require_api_key
def admin_update_flag(flag_id: int):
    try:
        row = LoanFlag.query.get_or_404(flag_id)
        data = request.get_json() or {}
        status = (data.get('status') or '').strip().lower()
        note = (data.get('note') or '').strip()
        if status in ('pending', 'resolved'):
            row.status = status
            if status == 'resolved' and not row.resolved_at:
                from datetime import datetime as _dt, timezone as _tz
                row.resolved_at = _dt.now(_tz.utc)
        if note:
            row.admin_note = note
        db.session.commit()
        return jsonify({'message': 'updated'})
    except Exception as e:
        logger.exception('admin_update_flag failed')
        db.session.rollback()
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500

# --- Admin: Newsletters management (list/view/update) ---
@api_bp.route('/admin/newsletters', methods=['GET'])
@require_api_key
def admin_list_newsletters():
    try:
        q = Newsletter.query
        team_id = request.args.get('team', type=int)
        if team_id:
            q = q.filter(Newsletter.team_id == team_id)
        published_only = request.args.get('published_only')
        if published_only is not None:
            want = str(published_only).lower() in ('true','1','yes','y')
            q = q.filter(Newsletter.published.is_(want))
        # week range filter
        week_start_str = request.args.get('week_start')
        week_end_str = request.args.get('week_end')
        if week_start_str and week_end_str:
            try:
                ws = datetime.strptime(week_start_str, '%Y-%m-%d').date()
                we = datetime.strptime(week_end_str, '%Y-%m-%d').date()
                q = q.filter(
                    db.and_(
                        Newsletter.week_start_date <= we,
                        Newsletter.week_end_date >= ws,
                    )
                )
            except ValueError:
                pass
        # issue_date (date of the newsletter context) range filter – primary filter
        issue_start_str = request.args.get('issue_start')
        issue_end_str = request.args.get('issue_end')
        if issue_start_str and issue_end_str:
            try:
                isd = datetime.strptime(issue_start_str, '%Y-%m-%d').date()
                ied = datetime.strptime(issue_end_str, '%Y-%m-%d').date()
                q = q.filter(
                    db.and_(
                        Newsletter.issue_date >= isd,
                        Newsletter.issue_date <= ied,
                    )
                )
            except ValueError:
                pass
        # created (generated_date) range filter
        created_start_str = request.args.get('created_start')
        created_end_str = request.args.get('created_end')
        if created_start_str and created_end_str:
            try:
                cs = datetime.strptime(created_start_str, '%Y-%m-%d').date()
                ce = datetime.strptime(created_end_str, '%Y-%m-%d').date()
                # generated_date is a DateTime – compare against start/end of day
                cs_dt = datetime.combine(cs, datetime.min.time(), tzinfo=timezone.utc)
                ce_dt = datetime.combine(ce, datetime.max.time(), tzinfo=timezone.utc)
                q = q.filter(
                    db.and_(
                        Newsletter.generated_date >= cs_dt,
                        Newsletter.generated_date <= ce_dt,
                    )
                )
            except ValueError:
                pass
        page = request.args.get('page', type=int) or 1
        if page < 1:
            page = 1

        page_size_param = request.args.get('page_size', type=int)
        page_size = None
        if page_size_param is not None:
            page_size = page_size_param
            if page_size < 1:
                page_size = 1
            if page_size > 200:
                page_size = 200

        total = q.order_by(None).count()

        total_pages = 1
        if page_size is not None:
            total_pages = max(1, math.ceil(total / page_size))
            if page > total_pages:
                page = total_pages
        else:
            page = 1

        # Ordering: issue date first if provided, otherwise created desc
        if issue_start_str and issue_end_str:
            q = q.order_by(Newsletter.issue_date.desc(), Newsletter.generated_date.desc())
        else:
            q = q.order_by(Newsletter.generated_date.desc())

        if page_size is not None:
            offset = (page - 1) * page_size
            if offset < 0:
                offset = 0
            q = q.offset(offset).limit(page_size)

        rows = q.all()
        effective_page_size = page_size if page_size is not None else total
        return jsonify({
            'items': [r.to_dict() for r in rows],
            'page': page,
            'page_size': effective_page_size,
            'total': total,
            'total_pages': total_pages,
        })
    except Exception as e:
        logger.exception('admin_list_newsletters failed')
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500

@api_bp.route('/admin/newsletters/<int:nid>', methods=['GET'])
@require_api_key
def admin_get_newsletter(nid: int):
    try:
        n = Newsletter.query.get_or_404(nid)
        return jsonify(n.to_dict())
    except Exception as e:
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500

@api_bp.route('/admin/newsletters/<int:nid>', methods=['PUT'])
@require_api_key
def admin_update_newsletter(nid: int):
    try:
        n = Newsletter.query.get_or_404(nid)
        data = request.get_json() or {}
        # Update title
        if 'title' in data:
            n.title = (data.get('title') or '').strip() or n.title
        # Update content
        if 'content_json' in data:
            payload = data.get('content_json')
            try:
                if isinstance(payload, str):
                    obj = json.loads(payload)
                else:
                    obj = payload
            except Exception:
                return jsonify({'error': 'content_json must be valid JSON'}), 400
            content_str = json.dumps(obj, ensure_ascii=False)
            n.content = content_str
            n.structured_content = content_str
        # Update week/issue dates (optional)
        def _parse_date(s):
            try:
                return datetime.strptime(s, '%Y-%m-%d').date()
            except Exception:
                return None
        if 'issue_date' in data and data.get('issue_date'):
            d = _parse_date(str(data.get('issue_date')))
            if d:
                n.issue_date = d
        if 'week_start_date' in data and data.get('week_start_date'):
            d = _parse_date(str(data.get('week_start_date')))
            if d:
                n.week_start_date = d
        if 'week_end_date' in data and data.get('week_end_date'):
            d = _parse_date(str(data.get('week_end_date')))
            if d:
                n.week_end_date = d
        # Publish/unpublish toggle
        auto_send_trigger = False
        if 'published' in data:
            want_pub = bool(data.get('published'))
            # Detect transition from not published -> published
            auto_send_trigger = (want_pub is True and not n.published)
            n.published = want_pub
            if want_pub:
                n.published_date = datetime.now(timezone.utc)
            else:
                n.published_date = None
        n.updated_at = datetime.now(timezone.utc)
        db.session.commit()

        # Optional: auto-send on approval
        _maybe_auto_send_on_publish(n, auto_send_trigger)

        return jsonify({'message': 'updated', 'newsletter': n.to_dict()})
    except Exception as e:
        logger.exception('admin_update_newsletter failed')
        db.session.rollback()
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500


@api_bp.route('/admin/newsletters/bulk-publish', methods=['POST'])
@require_api_key
def admin_bulk_publish_newsletters():
    try:
        data = request.get_json() or {}
        raw_ids = data.get('ids') or []
        publish_flag = bool(data.get('publish'))
        if not isinstance(raw_ids, list) or not raw_ids:
            return jsonify({'error': 'ids array required'}), 400

        ids = []
        for value in raw_ids:
            try:
                ids.append(int(value))
            except (TypeError, ValueError):
                continue
        ids = list(dict.fromkeys([i for i in ids if i > 0]))
        if not ids:
            return jsonify({'error': 'No valid newsletter ids provided'}), 400

        rows = Newsletter.query.filter(Newsletter.id.in_(ids)).all()
        found_ids = {row.id for row in rows}
        missing = [i for i in ids if i not in found_ids]

        now = datetime.now(timezone.utc)
        updated = 0
        auto_send_targets = []
        for row in rows:
            was_published = row.published
            if publish_flag:
                if not was_published:
                    row.published = True
                    row.published_date = now
                    updated += 1
                    auto_send_targets.append(row)
            else:
                if was_published:
                    row.published = False
                    row.published_date = None
                    updated += 1
        db.session.commit()

        logger.info(
            'Admin bulk publish user=%s publish=%s updated=%s ids=%s missing=%s',
            getattr(g, 'user_email', None),
            publish_flag,
            updated,
            ids,
            missing,
        )

        if publish_flag and auto_send_targets:
            for target in auto_send_targets:
                _maybe_auto_send_on_publish(target, auto_send_trigger=True)

        return jsonify({
            'updated': updated,
            'missing': missing,
            'publish': publish_flag,
            'total_requested': len(ids),
        })
    except Exception as e:
        logger.exception('admin_bulk_publish_newsletters failed')
        db.session.rollback()
        return jsonify(_safe_error_payload(e, 'Failed to update newsletter status. Please try again later.')), 500

# --- Simple run-history using AdminSetting key 'run_history' ---

def _get_run_history_list() -> list:
    row = AdminSetting.query.filter_by(key='run_history').first()
    if not row or not row.value_json:
        return []
    try:
        return json.loads(row.value_json) or []
    except Exception:
        return []

def _save_run_history_list(items: list):
    row = AdminSetting.query.filter_by(key='run_history').first()
    if not row:
        row = AdminSetting(key='run_history', value_json=json.dumps(items))
        db.session.add(row)
    else:
        row.value_json = json.dumps(items)
    db.session.commit()

def _append_run_history(event: dict):
    try:
        event = dict(event or {})
        event['ts'] = datetime.now(timezone.utc).isoformat()
        items = _get_run_history_list()
        items.insert(0, event)
        _save_run_history_list(items[:200])
    except Exception:
        db.session.rollback()
        logger.exception('append_run_history failed')


def _maybe_auto_send_on_publish(n: Newsletter, auto_send_trigger: bool):
    """Attempt to auto-send a newsletter after it is published."""
    if not auto_send_trigger:
        return None
    try:
        if os.getenv('NEWSLETTER_AUTO_SEND_ON_APPROVAL', '1').lower() not in ('1', 'true', 'yes'):
            return None
        if n.email_sent:
            return None

        out = _deliver_newsletter_via_webhook(n)
        logger.info(
            "Auto-send newsletter %s to team %s - status=%s", n.id, n.team_id, out.get('status')
        )

        if out.get('status') == 'ok':
            from datetime import datetime as _dt, timezone as _tz

            subs = UserSubscription.query.filter_by(team_id=n.team_id, active=True).all()
            valid_subs = [s for s in subs if (s.email or '').strip() and not s.email_bounced]
            used_count = len(valid_subs)
            n.email_sent = True
            n.email_sent_date = _dt.now(_tz.utc)
            n.subscriber_count = used_count

            try:
                ts = n.email_sent_date
                for s in valid_subs:
                    s.last_email_sent = ts
            except Exception:
                pass

            db.session.commit()

        try:
            _append_run_history({
                'kind': 'newsletter-auto-send',
                'newsletter_id': n.id,
                'team_id': n.team_id,
                'status': out.get('status'),
                'http_status': out.get('http_status'),
                'recipient_count': out.get('recipient_count'),
            })
        except Exception:
            pass

        return out
    except Exception:
        logger.exception('auto-send on approval failed')
        try:
            db.session.rollback()
        except Exception:
            pass
        return None

@api_bp.route('/admin/runs/history', methods=['GET', 'POST'])
@require_api_key
def admin_runs_history():
    try:
        if request.method == 'GET':
            return jsonify(_get_run_history_list())
        _append_run_history(request.get_json() or {})
        return jsonify({'message': 'appended'})
    except Exception as e:
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500

@api_bp.route('/admin/runs/history/clear', methods=['POST'])
@require_api_key
def admin_runs_history_clear():
    try:
        _save_run_history_list([])
        return jsonify({'message': 'cleared'})
    except Exception as e:
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500
