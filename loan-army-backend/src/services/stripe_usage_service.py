"""Service for recording Stripe metered usage (newsletters published)"""
import stripe
import logging
from src.models.league import db, StripeSubscription, UserAccount
from src.config.stripe_config import STRIPE_SECRET_KEY

logger = logging.getLogger(__name__)


def _stripe_request(method: str, url: str, params: dict | None = None):
    requestor = stripe._api_requestor._APIRequestor()
    return requestor.request(method, url, params=params, base_address='api')


def _meter_event_name(journalist_user_id: int) -> str:
    return f"gol_newsletter_{journalist_user_id}"


def record_newsletter_publication(journalist_user_id: int, newsletter_id: int, quantity: int = 1):
    """Record a newsletter publication as metered usage for all subscribers
    
    This should be called whenever a journalist publishes a newsletter.
    It records usage in Stripe so subscribers are charged at the end of their billing period.
    
    Args:
        journalist_user_id: ID of the journalist who published the newsletter
        newsletter_id: ID of the published newsletter
        quantity: Number of usage units (default 1 per newsletter)
        
    Returns:
        dict with success/failure counts
    """
    try:
        # Get all active subscriptions for this journalist
        active_subscriptions = StripeSubscription.query.filter_by(
            journalist_user_id=journalist_user_id,
            status='active'
        ).all()
        
        if not active_subscriptions:
            logger.info(f"No active subscribers for journalist {journalist_user_id}, skipping usage recording")
            return {'success': 0, 'failed': 0, 'message': 'No active subscribers'}
        
        success_count = 0
        failed_count = 0
        errors = []
        
        event_name = _meter_event_name(journalist_user_id)

        for subscription in active_subscriptions:
            try:
                if not subscription.stripe_customer_id:
                    logger.error(f"Missing stripe_customer_id for subscription {subscription.id}")
                    failed_count += 1
                    continue

                identifier = f"newsletter_{newsletter_id}_subscriber_{subscription.subscriber_user_id}"

                _stripe_request('post', '/v1/billing/meter_events', params={
                    'event_name': event_name,
                    'identifier': identifier,
                    'payload': {
                        'stripe_customer_id': subscription.stripe_customer_id,
                        'value': quantity
                    }
                })

                success_count += 1
                logger.info(
                    f"Recorded meter event for subscriber {subscription.subscriber_user_id}: "
                    f"newsletter {newsletter_id}"
                )

            except stripe.error.StripeError as e:
                logger.error(
                    f"Stripe error recording usage for subscription {subscription.stripe_subscription_id}: {e}"
                )
                failed_count += 1
                errors.append(str(e))
            except Exception as e:
                logger.error(
                    f"Error recording usage for subscription {subscription.stripe_subscription_id}: {e}"
                )
                failed_count += 1
                errors.append(str(e))
        
        result = {
            'success': success_count,
            'failed': failed_count,
            'total_subscribers': len(active_subscriptions),
            'journalist_user_id': journalist_user_id,
            'newsletter_id': newsletter_id
        }
        
        if errors:
            result['errors'] = errors
        
        logger.info(
            f"Newsletter {newsletter_id} usage recording complete: "
            f"{success_count} success, {failed_count} failed"
        )
        
        return result
        
    except Exception as e:
        logger.exception(f"Failed to record newsletter publication usage: {e}")
        return {
            'success': 0,
            'failed': 0,
            'error': str(e)
        }


def get_subscriber_usage_for_period(subscriber_user_id: int, journalist_user_id: int):
    """Get how many newsletters a subscriber has been charged for in current billing period
    
    Args:
        subscriber_user_id: ID of the subscriber
        journalist_user_id: ID of the journalist
        
    Returns:
        dict with usage information
    """
    try:
        subscription = StripeSubscription.query.filter_by(
            subscriber_user_id=subscriber_user_id,
            journalist_user_id=journalist_user_id,
            status='active'
        ).first()
        
        if not subscription:
            return {'error': 'No active subscription found'}
        
        # Get subscription from Stripe
        stripe_subscription = stripe.Subscription.retrieve(
            subscription.stripe_subscription_id
        )
        
        if not stripe_subscription.items or len(stripe_subscription.items.data) == 0:
            return {'error': 'No subscription items found'}
        
        subscription_item_id = stripe_subscription.items.data[0].id
        
        # Get usage records for current period
        usage_records = stripe.SubscriptionItem.list_usage_record_summaries(
            subscription_item_id,
            limit=100
        )
        
        # The first record should be for the current period
        current_period_usage = 0
        if usage_records.data:
            current_period_usage = usage_records.data[0].total_usage
        
        return {
            'subscriber_user_id': subscriber_user_id,
            'journalist_user_id': journalist_user_id,
            'subscription_id': subscription.stripe_subscription_id,
            'subscription_item_id': subscription_item_id,
            'current_period_usage': current_period_usage,
            'current_period_start': subscription.current_period_start.isoformat() if subscription.current_period_start else None,
            'current_period_end': subscription.current_period_end.isoformat() if subscription.current_period_end else None
        }
        
    except Exception as e:
        logger.exception(f"Error getting subscriber usage: {e}")
        return {'error': str(e)}
