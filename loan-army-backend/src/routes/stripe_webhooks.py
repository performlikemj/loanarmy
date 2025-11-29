"""Stripe webhook handlers"""
from flask import Blueprint, request, jsonify
import stripe
import logging
from src.models.league import db, StripeConnectedAccount, StripeSubscription, StripePlatformRevenue
from src.config.stripe_config import STRIPE_WEBHOOK_SECRET, calculate_platform_fee
from datetime import datetime, timezone, date, timedelta

stripe_webhooks_bp = Blueprint('stripe_webhooks', __name__)
logger = logging.getLogger(__name__)


@stripe_webhooks_bp.route('/stripe/webhook', methods=['POST'])
def handle_webhook():
    """Handle Stripe webhook events"""
    payload = request.data
    sig_header = request.headers.get('Stripe-Signature')
    
    if not sig_header:
        logger.error("No Stripe signature header found")
        return jsonify({'error': 'No signature'}), 400
    
    try:
        # Verify webhook signature
        event = stripe.Webhook.construct_event(
            payload, sig_header, STRIPE_WEBHOOK_SECRET
        )
    except ValueError as e:
        logger.error(f"Invalid payload: {e}")
        return jsonify({'error': 'Invalid payload'}), 400
    except stripe.error.SignatureVerificationError as e:
        logger.error(f"Invalid signature: {e}")
        return jsonify({'error': 'Invalid signature'}), 400
    
    # Handle the event
    event_type = event['type']
    event_data = event['data']['object']
    
    logger.info(f"Received Stripe webhook: {event_type}")
    
    try:
        if event_type == 'account.updated':
            handle_account_updated(event_data)
        elif event_type == 'checkout.session.completed':
            handle_checkout_completed(event_data)
        elif event_type == 'customer.subscription.created':
            handle_subscription_created(event_data)
        elif event_type == 'customer.subscription.updated':
            handle_subscription_updated(event_data)
        elif event_type == 'customer.subscription.deleted':
            handle_subscription_deleted(event_data)
        elif event_type == 'invoice.payment_succeeded':
            handle_invoice_payment_succeeded(event_data)
        elif event_type == 'invoice.payment_failed':
            handle_invoice_payment_failed(event_data)
        else:
            logger.info(f"Unhandled event type: {event_type}")
    
    except Exception as e:
        logger.exception(f"Error handling webhook event {event_type}")
        # Return 200 to acknowledge receipt even if processing failed
        # Stripe will retry the webhook if we return an error
        return jsonify({'error': str(e)}), 500
    
    return jsonify({'status': 'success'}), 200


def handle_account_updated(account_data):
    """Handle account.updated event - update connected account status"""
    account_id = account_data['id']
    
    account_record = StripeConnectedAccount.query.filter_by(
        stripe_account_id=account_id
    ).first()
    
    if not account_record:
        logger.warning(f"Account {account_id} not found in database")
        return
    
    # Update account status
    account_record.charges_enabled = account_data.get('charges_enabled', False)
    account_record.payouts_enabled = account_data.get('payouts_enabled', False)
    account_record.details_submitted = account_data.get('details_submitted', False)
    account_record.onboarding_complete = (
        account_record.details_submitted and 
        account_record.charges_enabled and 
        account_record.payouts_enabled
    )
    account_record.updated_at = datetime.now(timezone.utc)
    
    db.session.commit()
    
    logger.info(f"Updated account {account_id}: onboarding_complete={account_record.onboarding_complete}")


def handle_checkout_completed(session_data):
    """Handle checkout.session.completed event"""
    # Extract metadata
    metadata = session_data.get('metadata', {})
    subscriber_user_id = metadata.get('subscriber_user_id')
    journalist_user_id = metadata.get('journalist_user_id')
    
    if not subscriber_user_id or not journalist_user_id:
        logger.warning("Missing user IDs in checkout session metadata")
        return
    
    subscription_id = session_data.get('subscription')
    customer_id = session_data.get('customer')
    
    if not subscription_id:
        logger.warning("No subscription ID in checkout session")
        return
    
    # The subscription should be created by customer.subscription.created event
    # But we can create it here if it doesn't exist
    existing = StripeSubscription.query.filter_by(
        stripe_subscription_id=subscription_id
    ).first()
    
    if not existing:
        # Fetch subscription details from Stripe
        try:
            stripe_sub = stripe.Subscription.retrieve(subscription_id)
            _create_or_update_subscription_from_stripe(
                stripe_sub,
                int(subscriber_user_id),
                int(journalist_user_id)
            )
        except stripe.error.StripeError as e:
            logger.error(f"Error retrieving subscription {subscription_id}: {e}")
    
    logger.info(f"Checkout completed: subscription {subscription_id}")


def handle_subscription_created(subscription_data):
    """Handle customer.subscription.created event"""
    subscription_id = subscription_data['id']
    metadata = subscription_data.get('metadata', {})
    
    subscriber_user_id = metadata.get('subscriber_user_id')
    journalist_user_id = metadata.get('journalist_user_id')
    
    if not subscriber_user_id or not journalist_user_id:
        logger.warning(f"Missing user IDs in subscription {subscription_id} metadata")
        return
    
    _create_or_update_subscription_from_stripe(
        subscription_data,
        int(subscriber_user_id),
        int(journalist_user_id)
    )
    
    logger.info(f"Subscription created: {subscription_id}")


def handle_subscription_updated(subscription_data):
    """Handle customer.subscription.updated event"""
    subscription_id = subscription_data['id']
    
    subscription = StripeSubscription.query.filter_by(
        stripe_subscription_id=subscription_id
    ).first()
    
    if not subscription:
        # Try to get metadata
        metadata = subscription_data.get('metadata', {})
        subscriber_user_id = metadata.get('subscriber_user_id')
        journalist_user_id = metadata.get('journalist_user_id')
        
        if subscriber_user_id and journalist_user_id:
            _create_or_update_subscription_from_stripe(
                subscription_data,
                int(subscriber_user_id),
                int(journalist_user_id)
            )
        else:
            logger.warning(f"Subscription {subscription_id} not found and no metadata")
        return
    
    # Update subscription status
    subscription.status = subscription_data['status']
    subscription.cancel_at_period_end = subscription_data.get('cancel_at_period_end', False)
    
    current_period_start = subscription_data.get('current_period_start')
    current_period_end = subscription_data.get('current_period_end')
    
    if current_period_start:
        subscription.current_period_start = datetime.fromtimestamp(current_period_start, tz=timezone.utc)
    if current_period_end:
        subscription.current_period_end = datetime.fromtimestamp(current_period_end, tz=timezone.utc)
    
    subscription.updated_at = datetime.now(timezone.utc)
    
    db.session.commit()
    
    logger.info(f"Subscription updated: {subscription_id}, status={subscription.status}")


def handle_subscription_deleted(subscription_data):
    """Handle customer.subscription.deleted event"""
    subscription_id = subscription_data['id']
    
    subscription = StripeSubscription.query.filter_by(
        stripe_subscription_id=subscription_id
    ).first()
    
    if not subscription:
        logger.warning(f"Subscription {subscription_id} not found for deletion")
        return
    
    subscription.status = 'canceled'
    subscription.updated_at = datetime.now(timezone.utc)
    
    db.session.commit()
    
    logger.info(f"Subscription deleted: {subscription_id}")


def handle_invoice_payment_succeeded(invoice_data):
    """Handle invoice.payment_succeeded event - track revenue"""
    subscription_id = invoice_data.get('subscription')
    
    if not subscription_id:
        return  # Not a subscription invoice
    
    # Get subscription to check if it's a journalist subscription
    subscription = StripeSubscription.query.filter_by(
        stripe_subscription_id=subscription_id
    ).first()
    
    if not subscription:
        logger.warning(f"Subscription {subscription_id} not found for invoice")
        return
    
    # Get invoice amount
    amount_paid = invoice_data.get('amount_paid', 0)  # in cents
    
    # Calculate platform fee
    platform_fee = calculate_platform_fee(amount_paid)
    
    # Update or create revenue record for this period
    today = date.today()
    period_start = today.replace(day=1)  # First day of month
    
    # Calculate last day of month
    if today.month == 12:
        period_end = date(today.year + 1, 1, 1) - timedelta(days=1)
    else:
        period_end = date(today.year, today.month + 1, 1) - timedelta(days=1)
    
    revenue_record = StripePlatformRevenue.query.filter_by(
        period_start=period_start,
        period_end=period_end
    ).first()
    
    if not revenue_record:
        revenue_record = StripePlatformRevenue(
            period_start=period_start,
            period_end=period_end,
            total_revenue_cents=0,
            platform_fee_cents=0,
            subscription_count=0
        )
        db.session.add(revenue_record)
    
    # Update revenue
    revenue_record.total_revenue_cents += amount_paid
    revenue_record.platform_fee_cents += platform_fee
    revenue_record.subscription_count = StripeSubscription.query.filter_by(status='active').count()
    
    db.session.commit()
    
    logger.info(f"Invoice payment succeeded: ${amount_paid / 100:.2f}, platform fee: ${platform_fee / 100:.2f}")


def handle_invoice_payment_failed(invoice_data):
    """Handle invoice.payment_failed event"""
    subscription_id = invoice_data.get('subscription')
    
    if not subscription_id:
        return
    
    subscription = StripeSubscription.query.filter_by(
        stripe_subscription_id=subscription_id
    ).first()
    
    if not subscription:
        return
    
    # Update status to past_due
    subscription.status = 'past_due'
    subscription.updated_at = datetime.now(timezone.utc)
    
    db.session.commit()
    
    logger.warning(f"Invoice payment failed for subscription {subscription_id}")


def _create_or_update_subscription_from_stripe(stripe_sub_data, subscriber_user_id: int, journalist_user_id: int):
    """Create or update subscription from Stripe data
    
    Args:
        stripe_sub_data: Stripe subscription object or dict
        subscriber_user_id: ID of subscriber user
        journalist_user_id: ID of journalist user
    """
    subscription_id = stripe_sub_data['id']
    
    # Check if exists
    subscription = StripeSubscription.query.filter_by(
        stripe_subscription_id=subscription_id
    ).first()
    
    if not subscription:
        subscription = StripeSubscription(
            subscriber_user_id=subscriber_user_id,
            journalist_user_id=journalist_user_id,
            stripe_subscription_id=subscription_id,
            stripe_customer_id=stripe_sub_data['customer'],
            status=stripe_sub_data['status']
        )
        db.session.add(subscription)
    else:
        subscription.status = stripe_sub_data['status']
    
    # Update periods
    current_period_start = stripe_sub_data.get('current_period_start')
    current_period_end = stripe_sub_data.get('current_period_end')
    
    if current_period_start:
        subscription.current_period_start = datetime.fromtimestamp(current_period_start, tz=timezone.utc)
    if current_period_end:
        subscription.current_period_end = datetime.fromtimestamp(current_period_end, tz=timezone.utc)
    
    subscription.cancel_at_period_end = stripe_sub_data.get('cancel_at_period_end', False)
    subscription.updated_at = datetime.now(timezone.utc)
    
    db.session.commit()

