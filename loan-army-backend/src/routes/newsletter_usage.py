"""Routes for recording newsletter publications and triggering usage billing"""
from flask import Blueprint, request, jsonify
import logging
from src.models.league import db, Newsletter, UserAccount
from src.routes.api import require_api_key, _safe_error_payload
from src.services.stripe_usage_service import record_newsletter_publication, get_subscriber_usage_for_period

newsletter_usage_bp = Blueprint('newsletter_usage', __name__)
logger = logging.getLogger(__name__)


@newsletter_usage_bp.route('/newsletters/<int:newsletter_id>/record-publication', methods=['POST'])
@require_api_key
def record_newsletter_for_billing(newsletter_id):
    """Record that a newsletter was published (for metered billing)
    
    This endpoint should be called whenever a newsletter is published.
    It records usage in Stripe so all subscribers are charged at the end of their billing period.
    """
    try:
        newsletter = Newsletter.query.get_or_404(newsletter_id)
        
        # Get the journalist who authored this newsletter
        # Assuming newsletters are linked to journalists via commentary or team assignments
        # You may need to adjust this based on your data model
        
        data = request.get_json() or {}
        journalist_user_id = data.get('journalist_user_id')
        
        if not journalist_user_id:
            return jsonify({'error': 'journalist_user_id is required'}), 400
        
        # Verify the journalist exists
        journalist = UserAccount.query.get(journalist_user_id)
        if not journalist or not journalist.is_journalist:
            return jsonify({'error': 'Invalid journalist'}), 404
        
        # Record the publication as usage
        result = record_newsletter_publication(
            journalist_user_id=journalist_user_id,
            newsletter_id=newsletter_id,
            quantity=1
        )
        
        if 'error' in result:
            return jsonify({
                'error': 'Failed to record newsletter publication',
                'details': result
            }), 500
        
        return jsonify({
            'message': 'Newsletter publication recorded for billing',
            'newsletter_id': newsletter_id,
            'journalist_user_id': journalist_user_id,
            'subscribers_charged': result['success'],
            'failed': result['failed'],
            'total_subscribers': result['total_subscribers']
        })
        
    except Exception as e:
        logger.exception("Error in record_newsletter_for_billing")
        return jsonify(_safe_error_payload(e, 'Failed to record newsletter publication')), 500


@newsletter_usage_bp.route('/newsletters/auto-record/<int:newsletter_id>', methods=['POST'])
def auto_record_newsletter_publication(newsletter_id):
    """Auto-trigger usage recording when a newsletter is published
    
    This can be called via webhook or newsletter publish flow.
    Doesn't require API key since it's triggered by internal events.
    """
    try:
        newsletter = Newsletter.query.get_or_404(newsletter_id)
        
        # Find the journalist based on newsletter commentary
        # This assumes newsletters have commentaries with authors
        from src.models.league import NewsletterCommentary
        
        commentary = NewsletterCommentary.query.filter_by(
            newsletter_id=newsletter_id
        ).first()
        
        if not commentary or not commentary.author_id:
            logger.warning(f"No commentary author found for newsletter {newsletter_id}")
            return jsonify({
                'message': 'No journalist found for this newsletter, skipping usage recording'
            }), 200
        
        journalist = UserAccount.query.get(commentary.author_id)
        if not journalist or not journalist.is_journalist:
            logger.warning(f"Author {commentary.author_id} is not a journalist")
            return jsonify({
                'message': 'Newsletter author is not a journalist, skipping usage recording'
            }), 200
        
        # Record the usage
        result = record_newsletter_publication(
            journalist_user_id=journalist.id,
            newsletter_id=newsletter_id,
            quantity=1
        )
        
        return jsonify({
            'message': 'Newsletter publication recorded',
            'newsletter_id': newsletter_id,
            'journalist_user_id': journalist.id,
            'result': result
        })
        
    except Exception as e:
        logger.exception("Error in auto_record_newsletter_publication")
        # Don't return error - this is a background operation
        return jsonify({
            'message': 'Failed to record usage',
            'error': str(e)
        }), 200  # Return 200 so it doesn't retry


@newsletter_usage_bp.route('/subscribers/usage', methods=['GET'])
def get_my_usage():
    """Get current billing period usage for authenticated subscriber"""
    try:
        # This would need to use the authentication system
        # For now, requiring explicit user_id and journalist_id parameters
        
        subscriber_user_id = request.args.get('subscriber_user_id', type=int)
        journalist_user_id = request.args.get('journalist_user_id', type=int)
        
        if not subscriber_user_id or not journalist_user_id:
            return jsonify({
                'error': 'subscriber_user_id and journalist_user_id are required'
            }), 400
        
        usage_info = get_subscriber_usage_for_period(
            subscriber_user_id=subscriber_user_id,
            journalist_user_id=journalist_user_id
        )
        
        return jsonify(usage_info)
        
    except Exception as e:
        logger.exception("Error in get_my_usage")
        return jsonify(_safe_error_payload(e, 'Failed to get usage')), 500

