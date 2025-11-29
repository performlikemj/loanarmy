"""Stripe routes for subscriber operations (checkout, subscriptions)"""
from flask import Blueprint, request, jsonify, g
import stripe
import logging
from src.models.league import db, UserAccount, StripeConnectedAccount, StripeSubscriptionPlan, StripeSubscription
from src.routes.api import require_user_auth, _safe_error_payload
from src.config.stripe_config import calculate_platform_fee, validate_stripe_config
from datetime import datetime, timezone

stripe_subscriber_bp = Blueprint('stripe_subscriber', __name__)
logger = logging.getLogger(__name__)


@stripe_subscriber_bp.route('/stripe/subscribe/<int:journalist_id>', methods=['POST'])
@require_user_auth
def create_checkout_session(journalist_id):
    """Create Stripe Checkout session to subscribe to a journalist"""
    try:
        user = g.user
        
        # Validate Stripe configuration
        is_valid, error_msg = validate_stripe_config()
        if not is_valid:
            return jsonify({'error': f'Stripe not configured: {error_msg}'}), 500
        
        # Get journalist
        journalist = UserAccount.query.get(journalist_id)
        if not journalist or not journalist.is_journalist:
            return jsonify({'error': 'Journalist not found'}), 404
        
        # Check if journalist has Stripe account
        stripe_account = StripeConnectedAccount.query.filter_by(
            journalist_user_id=journalist_id
        ).first()
        
        if not stripe_account or not stripe_account.onboarding_complete:
            return jsonify({'error': 'Journalist has not completed Stripe setup'}), 400
        
        # Get journalist's active price
        price_plan = StripeSubscriptionPlan.query.filter_by(
            journalist_user_id=journalist_id,
            is_active=True
        ).first()
        
        if not price_plan:
            return jsonify({'error': 'Journalist has not set a subscription price'}), 400
        
        # Check if already subscribed
        existing_sub = StripeSubscription.query.filter_by(
            subscriber_user_id=user.id,
            journalist_user_id=journalist_id,
            status='active'
        ).first()
        
        if existing_sub:
            return jsonify({'error': 'Already subscribed to this journalist'}), 400
        
        # Calculate platform fee (application fee)
        platform_fee = calculate_platform_fee(price_plan.price_amount)
        
        try:
            # Create or retrieve Stripe customer for the subscriber
            customer = _get_or_create_stripe_customer(user)
            
            # Get URLs from request
            data = request.get_json() or {}
            success_url = data.get('success_url', request.host_url + 'subscriptions?success=true')
            cancel_url = data.get('cancel_url', request.host_url + f'journalist/{journalist_id}')
            
            # Create Checkout Session with application fee for connected account
            checkout_session = stripe.checkout.Session.create(
                customer=customer.id,
                payment_method_types=['card'],
                line_items=[{
                    'price': price_plan.stripe_price_id,
                    'quantity': 1,
                }],
                mode='subscription',
                success_url=success_url + '&session_id={CHECKOUT_SESSION_ID}',
                cancel_url=cancel_url,
                payment_intent_data={
                    'application_fee_amount': platform_fee,
                    'transfer_data': {
                        'destination': stripe_account.stripe_account_id,
                    },
                },
                subscription_data={
                    'application_fee_percent': calculate_platform_fee(100),  # 10%
                    'metadata': {
                        'subscriber_user_id': user.id,
                        'journalist_user_id': journalist_id,
                        'subscriber_email': user.email,
                        'journalist_email': journalist.email
                    }
                },
                metadata={
                    'subscriber_user_id': user.id,
                    'journalist_user_id': journalist_id
                }
            )
            
            return jsonify({
                'checkout_url': checkout_session.url,
                'session_id': checkout_session.id,
                'price_amount': price_plan.price_amount,
                'price_display': f"${price_plan.price_amount / 100:.2f}",
                'journalist_name': journalist.display_name
            })
            
        except stripe.error.StripeError as e:
            logger.error(f"Stripe error creating checkout session: {e}")
            return jsonify({'error': f'Failed to create checkout session: {str(e)}'}), 500
            
    except Exception as e:
        logger.exception("Error in create_checkout_session")
        return jsonify(_safe_error_payload(e, 'Failed to create checkout session')), 500


@stripe_subscriber_bp.route('/stripe/create-customer', methods=['POST'])
@require_user_auth
def create_stripe_customer():
    """Create or retrieve Stripe customer for the current user"""
    try:
        user = g.user
        
        customer = _get_or_create_stripe_customer(user)
        
        return jsonify({
            'customer_id': customer.id,
            'email': customer.email
        })
        
    except Exception as e:
        logger.exception("Error in create_stripe_customer")
        return jsonify(_safe_error_payload(e, 'Failed to create customer')), 500


@stripe_subscriber_bp.route('/stripe/my-subscriptions', methods=['GET'])
@require_user_auth
def get_my_subscriptions():
    """List user's active Stripe subscriptions to journalists"""
    try:
        user = g.user
        
        subscriptions = StripeSubscription.query.filter_by(
            subscriber_user_id=user.id
        ).all()
        
        result = []
        for sub in subscriptions:
            journalist = UserAccount.query.get(sub.journalist_user_id)
            price_plan = StripeSubscriptionPlan.query.filter_by(
                journalist_user_id=sub.journalist_user_id,
                is_active=True
            ).first()
            
            sub_dict = sub.to_dict()
            sub_dict['journalist'] = {
                'id': journalist.id,
                'display_name': journalist.display_name,
                'email': journalist.email,
                'profile_image_url': journalist.profile_image_url
            } if journalist else None
            
            if price_plan:
                sub_dict['price'] = {
                    'amount': price_plan.price_amount,
                    'display': f"${price_plan.price_amount / 100:.2f}",
                    'currency': price_plan.currency
                }
            
            result.append(sub_dict)
        
        return jsonify({
            'subscriptions': result,
            'count': len(result)
        })
        
    except Exception as e:
        logger.exception("Error in get_my_subscriptions")
        return jsonify(_safe_error_payload(e, 'Failed to get subscriptions')), 500


@stripe_subscriber_bp.route('/stripe/cancel-subscription/<int:subscription_id>', methods=['POST'])
@require_user_auth
def cancel_subscription(subscription_id):
    """Cancel a subscription"""
    try:
        user = g.user
        
        # Get subscription from database
        subscription = StripeSubscription.query.get(subscription_id)
        
        if not subscription:
            return jsonify({'error': 'Subscription not found'}), 404
        
        # Verify ownership
        if subscription.subscriber_user_id != user.id:
            return jsonify({'error': 'Unauthorized'}), 403
        
        if subscription.status in ['canceled', 'incomplete_expired']:
            return jsonify({'error': 'Subscription already canceled'}), 400
        
        # Cancel in Stripe
        try:
            stripe_sub = stripe.Subscription.modify(
                subscription.stripe_subscription_id,
                cancel_at_period_end=True
            )
            
            # Update local record
            subscription.cancel_at_period_end = True
            subscription.updated_at = datetime.now(timezone.utc)
            db.session.commit()
            
            return jsonify({
                'message': 'Subscription will be canceled at the end of the billing period',
                'subscription': subscription.to_dict(),
                'cancels_at': subscription.current_period_end.isoformat() if subscription.current_period_end else None
            })
            
        except stripe.error.StripeError as e:
            logger.error(f"Stripe error canceling subscription: {e}")
            return jsonify({'error': f'Failed to cancel subscription: {str(e)}'}), 500
            
    except Exception as e:
        logger.exception("Error in cancel_subscription")
        return jsonify(_safe_error_payload(e, 'Failed to cancel subscription')), 500


@stripe_subscriber_bp.route('/stripe/reactivate-subscription/<int:subscription_id>', methods=['POST'])
@require_user_auth
def reactivate_subscription(subscription_id):
    """Reactivate a subscription that was set to cancel"""
    try:
        user = g.user
        
        subscription = StripeSubscription.query.get(subscription_id)
        
        if not subscription:
            return jsonify({'error': 'Subscription not found'}), 404
        
        if subscription.subscriber_user_id != user.id:
            return jsonify({'error': 'Unauthorized'}), 403
        
        if not subscription.cancel_at_period_end:
            return jsonify({'error': 'Subscription is not set to cancel'}), 400
        
        try:
            # Update Stripe subscription
            stripe_sub = stripe.Subscription.modify(
                subscription.stripe_subscription_id,
                cancel_at_period_end=False
            )
            
            # Update local record
            subscription.cancel_at_period_end = False
            subscription.updated_at = datetime.now(timezone.utc)
            db.session.commit()
            
            return jsonify({
                'message': 'Subscription reactivated successfully',
                'subscription': subscription.to_dict()
            })
            
        except stripe.error.StripeError as e:
            logger.error(f"Stripe error reactivating subscription: {e}")
            return jsonify({'error': f'Failed to reactivate subscription: {str(e)}'}), 500
            
    except Exception as e:
        logger.exception("Error in reactivate_subscription")
        return jsonify(_safe_error_payload(e, 'Failed to reactivate subscription')), 500


def _get_or_create_stripe_customer(user: UserAccount) -> stripe.Customer:
    """Get or create a Stripe customer for a user
    
    Args:
        user: UserAccount object
        
    Returns:
        Stripe Customer object
    """
    # Search for existing customer by email
    customers = stripe.Customer.list(email=user.email, limit=1)
    
    if customers.data:
        return customers.data[0]
    
    # Create new customer
    customer = stripe.Customer.create(
        email=user.email,
        name=user.display_name,
        metadata={
            'user_id': user.id,
            'display_name': user.display_name
        }
    )
    
    return customer

