"""Stripe routes for journalist operations (onboarding, pricing, dashboard)"""
from flask import Blueprint, request, jsonify, g
import stripe
import logging
from src.models.league import db, UserAccount, StripeConnectedAccount, StripeSubscriptionPlan
from src.routes.api import require_user_auth, _safe_error_payload
from src.config.stripe_config import (
    STRIPE_SECRET_KEY, 
    calculate_platform_fee, 
    PLATFORM_FEE_PERCENT,
    validate_stripe_config
)
from datetime import datetime, timezone

stripe_journalist_bp = Blueprint('stripe_journalist', __name__)
logger = logging.getLogger(__name__)


def _stripe_request(method: str, url: str, params: dict | None = None):
    requestor = stripe._api_requestor._APIRequestor()
    return requestor.request(method, url, params=params, base_address='api')


def _meter_event_name(journalist_user_id: int) -> str:
    return f"gol_newsletter_{journalist_user_id}"


def _get_or_create_meter_for_journalist(user: UserAccount):
    event_name = _meter_event_name(user.id)
    try:
        meters = _stripe_request('get', '/v1/billing/meters', params={'limit': 100, 'status': 'active'})
        for meter in getattr(meters, 'data', []) or []:
            meter_event = getattr(meter, 'event_name', None) or meter.get('event_name')
            if meter_event == event_name:
                return meter
    except Exception as e:
        logger.warning(f"Failed to list meters for journalist {user.id}: {e}")

    display_name = f"Go On Loan - {user.display_name} newsletter usage"
    return _stripe_request('post', '/v1/billing/meters', params={
        'display_name': display_name,
        'event_name': event_name,
        'default_aggregation': {'formula': 'sum'},
        'customer_mapping': {
            'type': 'by_id',
            'event_payload_key': 'stripe_customer_id'
        },
        'value_settings': {
            'event_payload_key': 'value'
        }
    })

@stripe_journalist_bp.route('/stripe/journalist/onboard', methods=['POST'])
@require_user_auth
def create_onboarding():
    """Create Stripe Connect Express account and return onboarding link"""
    try:
        user = g.user
        
        # Check if user is a journalist
        if not user.is_journalist:
            return jsonify({'error': 'Only journalists can create Stripe Connect accounts'}), 403
        
        # Validate Stripe configuration
        is_valid, error_msg = validate_stripe_config()
        if not is_valid:
            return jsonify({'error': f'Stripe not configured: {error_msg}'}), 500
        
        # Check if account already exists
        existing_account = StripeConnectedAccount.query.filter_by(
            journalist_user_id=user.id
        ).first()
        
        if existing_account:
            # Generate new onboarding link for existing account
            try:
                account_link = stripe.AccountLink.create(
                    account=existing_account.stripe_account_id,
                    refresh_url=request.json.get('refresh_url', request.host_url + 'journalist/stripe-setup'),
                    return_url=request.json.get('return_url', request.host_url + 'journalist/stripe-setup?success=true'),
                    type='account_onboarding',
                )
                
                return jsonify({
                    'onboarding_url': account_link.url,
                    'account_id': existing_account.stripe_account_id,
                    'existing': True
                })
            except stripe.error.InvalidRequestError as e:
                logger.error(f"Error generating onboarding link for existing account: {e}")
                return jsonify({'error': 'Failed to generate onboarding link'}), 500
        
        # Create new Stripe Connect Express account
        try:
            account = stripe.Account.create(
                type='express',
                country='US',  # Default to US, could be made configurable
                email=user.email,
                capabilities={
                    'card_payments': {'requested': True},
                    'transfers': {'requested': True},
                },
                business_type='individual',
                metadata={
                    'user_id': user.id,
                    'email': user.email,
                    'display_name': user.display_name
                }
            )
            
            # Save to database
            new_account = StripeConnectedAccount(
                journalist_user_id=user.id,
                stripe_account_id=account.id,
                onboarding_complete=False,
                payouts_enabled=False,
                charges_enabled=False,
                details_submitted=False
            )
            db.session.add(new_account)
            db.session.commit()
            
            # Create account link for onboarding
            account_link = stripe.AccountLink.create(
                account=account.id,
                refresh_url=request.json.get('refresh_url', request.host_url + 'journalist/stripe-setup'),
                return_url=request.json.get('return_url', request.host_url + 'journalist/stripe-setup?success=true'),
                type='account_onboarding',
            )
            
            return jsonify({
                'onboarding_url': account_link.url,
                'account_id': account.id,
                'existing': False
            }), 201
            
        except stripe.error.StripeError as e:
            logger.error(f"Stripe error creating account: {e}")
            return jsonify({'error': f'Failed to create Stripe account: {str(e)}'}), 500
            
    except Exception as e:
        logger.exception("Error in create_onboarding")
        return jsonify(_safe_error_payload(e, 'Failed to create onboarding')), 500


@stripe_journalist_bp.route('/stripe/journalist/account-status', methods=['GET'])
@require_user_auth
def get_account_status():
    """Get journalist's Stripe Connect account status"""
    try:
        user = g.user
        
        if not user.is_journalist:
            return jsonify({'error': 'Only journalists can check account status'}), 403
        
        account_record = StripeConnectedAccount.query.filter_by(
            journalist_user_id=user.id
        ).first()
        
        if not account_record:
            return jsonify({
                'has_account': False,
                'onboarding_complete': False
            })
        
        # Fetch latest status from Stripe
        try:
            account = stripe.Account.retrieve(account_record.stripe_account_id)
            
            # Update local record
            account_record.charges_enabled = account.charges_enabled
            account_record.payouts_enabled = account.payouts_enabled
            account_record.details_submitted = account.details_submitted
            account_record.onboarding_complete = (
                account.details_submitted and 
                account.charges_enabled and 
                account.payouts_enabled
            )
            account_record.updated_at = datetime.now(timezone.utc)
            db.session.commit()
            
            return jsonify({
                'has_account': True,
                'account_id': account_record.stripe_account_id,
                'onboarding_complete': account_record.onboarding_complete,
                'charges_enabled': account_record.charges_enabled,
                'payouts_enabled': account_record.payouts_enabled,
                'details_submitted': account_record.details_submitted,
                'requirements': {
                    'currently_due': account.requirements.currently_due if account.requirements else [],
                    'eventually_due': account.requirements.eventually_due if account.requirements else [],
                }
            })
            
        except stripe.error.StripeError as e:
            logger.error(f"Error retrieving Stripe account: {e}")
            return jsonify({'error': 'Failed to retrieve account status'}), 500
            
    except Exception as e:
        logger.exception("Error in get_account_status")
        return jsonify(_safe_error_payload(e, 'Failed to get account status')), 500


@stripe_journalist_bp.route('/stripe/journalist/refresh-onboard', methods=['POST'])
@require_user_auth
def refresh_onboarding():
    """Generate new onboarding link for incomplete onboarding"""
    try:
        user = g.user
        
        if not user.is_journalist:
            return jsonify({'error': 'Only journalists can refresh onboarding'}), 403
        
        account_record = StripeConnectedAccount.query.filter_by(
            journalist_user_id=user.id
        ).first()
        
        if not account_record:
            return jsonify({'error': 'No Stripe account found. Please create one first.'}), 404
        
        if account_record.onboarding_complete:
            return jsonify({'error': 'Onboarding already complete'}), 400
        
        # Generate new account link
        try:
            account_link = stripe.AccountLink.create(
                account=account_record.stripe_account_id,
                refresh_url=request.json.get('refresh_url', request.host_url + 'journalist/stripe-setup'),
                return_url=request.json.get('return_url', request.host_url + 'journalist/stripe-setup?success=true'),
                type='account_onboarding',
            )
            
            return jsonify({
                'onboarding_url': account_link.url,
                'account_id': account_record.stripe_account_id
            })
            
        except stripe.error.StripeError as e:
            logger.error(f"Error generating new onboarding link: {e}")
            return jsonify({'error': 'Failed to generate onboarding link'}), 500
            
    except Exception as e:
        logger.exception("Error in refresh_onboarding")
        return jsonify(_safe_error_payload(e, 'Failed to refresh onboarding')), 500


@stripe_journalist_bp.route('/stripe/journalist/dashboard-link', methods=['POST'])
@require_user_auth
def get_dashboard_link():
    """Generate Stripe Express dashboard link for journalist"""
    try:
        user = g.user
        
        if not user.is_journalist:
            return jsonify({'error': 'Only journalists can access dashboard'}), 403
        
        account_record = StripeConnectedAccount.query.filter_by(
            journalist_user_id=user.id
        ).first()
        
        if not account_record:
            return jsonify({'error': 'No Stripe account found'}), 404
        
        if not account_record.onboarding_complete:
            return jsonify({'error': 'Onboarding must be completed first'}), 400
        
        # Generate login link for Express dashboard
        try:
            login_link = stripe.Account.create_login_link(
                account_record.stripe_account_id
            )
            
            return jsonify({
                'dashboard_url': login_link.url
            })
            
        except stripe.error.StripeError as e:
            logger.error(f"Error generating dashboard link: {e}")
            return jsonify({'error': 'Failed to generate dashboard link'}), 500
            
    except Exception as e:
        logger.exception("Error in get_dashboard_link")
        return jsonify(_safe_error_payload(e, 'Failed to get dashboard link')), 500


@stripe_journalist_bp.route('/stripe/journalist/create-price', methods=['POST'])
@require_user_auth
def create_subscription_price():
    """Create Stripe product and price for journalist's subscription"""
    try:
        user = g.user
        
        if not user.is_journalist:
            return jsonify({'error': 'Only journalists can create subscription prices'}), 403
        
        # Check if onboarding is complete
        account_record = StripeConnectedAccount.query.filter_by(
            journalist_user_id=user.id
        ).first()
        
        if not account_record or not account_record.onboarding_complete:
            return jsonify({'error': 'Stripe onboarding must be completed first'}), 400
        
        data = request.get_json() or {}
        price_dollars = data.get('price')
        
        if not price_dollars or not isinstance(price_dollars, (int, float)) or price_dollars <= 0:
            return jsonify({'error': 'Valid price (in dollars) is required'}), 400
        
        price_cents = int(price_dollars * 100)
        
        # Check if journalist already has an active price
        existing_plan = StripeSubscriptionPlan.query.filter_by(
            journalist_user_id=user.id,
            is_active=True
        ).first()
        
        try:
            # Create or retrieve product
            if existing_plan:
                product_id = existing_plan.stripe_product_id
            else:
                product = stripe.Product.create(
                    name=f"{user.display_name}'s Subscription",
                    description=f"Monthly subscription to {user.display_name}'s content on Go On Loan",
                    metadata={
                        'journalist_user_id': user.id,
                        'journalist_email': user.email
                    }
                )
                product_id = product.id
            
            meter = _get_or_create_meter_for_journalist(user)
            meter_id = getattr(meter, 'id', None) or meter.get('id')
            if not meter_id:
                raise ValueError("Stripe meter creation failed")

            # Create price with metered billing (charge per newsletter published)
            price = stripe.Price.create(
                product=product_id,
                unit_amount=price_cents,
                currency='usd',
                recurring={
                    'interval': 'month',
                    'usage_type': 'metered',  # Only charge when newsletters are published
                    'aggregate_usage': 'sum',  # Sum up all newsletters in the billing period
                    'meter': meter_id
                },
                billing_scheme='per_unit',  # Charge per newsletter
                metadata={
                    'journalist_user_id': user.id,
                    'platform_fee_percent': PLATFORM_FEE_PERCENT,
                    'billing_type': 'metered_per_newsletter',
                    'meter_id': meter_id,
                    'meter_event_name': _meter_event_name(user.id)
                }
            )
            
            # Deactivate old price if exists
            if existing_plan:
                existing_plan.is_active = False
            
            # Save new price to database
            new_plan = StripeSubscriptionPlan(
                journalist_user_id=user.id,
                stripe_product_id=product_id,
                stripe_price_id=price.id,
                price_amount=price_cents,
                currency='usd',
                is_active=True
            )
            db.session.add(new_plan)
            db.session.commit()
            
            platform_fee = calculate_platform_fee(price_cents)
            journalist_receives = price_cents - platform_fee
            
            return jsonify({
                'message': 'Subscription price created successfully',
                'plan': new_plan.to_dict(),
                'breakdown': {
                    'total': price_cents,
                    'total_display': f"${price_cents / 100:.2f}",
                    'journalist_receives': journalist_receives,
                    'journalist_receives_display': f"${journalist_receives / 100:.2f}",
                    'platform_fee': platform_fee,
                    'platform_fee_display': f"${platform_fee / 100:.2f}",
                    'platform_fee_percent': PLATFORM_FEE_PERCENT
                }
            }), 201
            
        except stripe.error.StripeError as e:
            logger.error(f"Stripe error creating price: {e}")
            return jsonify({'error': f'Failed to create price: {str(e)}'}), 500
            
    except Exception as e:
        logger.exception("Error in create_subscription_price")
        return jsonify(_safe_error_payload(e, 'Failed to create subscription price')), 500


@stripe_journalist_bp.route('/stripe/journalist/my-price', methods=['GET'])
@require_user_auth
def get_my_price():
    """Get journalist's current active subscription price"""
    try:
        user = g.user
        
        if not user.is_journalist:
            return jsonify({'error': 'Only journalists can view their prices'}), 403
        
        active_plan = StripeSubscriptionPlan.query.filter_by(
            journalist_user_id=user.id,
            is_active=True
        ).first()
        
        if not active_plan:
            return jsonify({
                'has_price': False,
                'message': 'No active subscription price set'
            })
        
        platform_fee = calculate_platform_fee(active_plan.price_amount)
        journalist_receives = active_plan.price_amount - platform_fee
        
        return jsonify({
            'has_price': True,
            'plan': active_plan.to_dict(),
            'breakdown': {
                'total': active_plan.price_amount,
                'total_display': f"${active_plan.price_amount / 100:.2f}",
                'journalist_receives': journalist_receives,
                'journalist_receives_display': f"${journalist_receives / 100:.2f}",
                'platform_fee': platform_fee,
                'platform_fee_display': f"${platform_fee / 100:.2f}",
                'platform_fee_percent': PLATFORM_FEE_PERCENT
            }
        })
        
    except Exception as e:
        logger.exception("Error in get_my_price")
        return jsonify(_safe_error_payload(e, 'Failed to get price')), 500


@stripe_journalist_bp.route('/stripe/journalist/update-price', methods=['PUT'])
@require_user_auth
def update_subscription_price():
    """Update journalist's subscription price (creates new price, archives old)"""
    try:
        user = g.user
        
        if not user.is_journalist:
            return jsonify({'error': 'Only journalists can update prices'}), 403
        
        # Use the same logic as create_price (it already handles updates)
        return create_subscription_price()
        
    except Exception as e:
        logger.exception("Error in update_subscription_price")
        return jsonify(_safe_error_payload(e, 'Failed to update price')), 500
