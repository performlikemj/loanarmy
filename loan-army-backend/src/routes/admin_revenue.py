"""Admin routes for viewing platform revenue and maintenance fees"""
from flask import Blueprint, request, jsonify
import logging
from src.models.league import db, StripePlatformRevenue, StripeSubscription
from src.routes.api import require_api_key
from src.config.stripe_config import PLATFORM_FEE_PERCENT, calculate_platform_fee
from datetime import datetime, date, timedelta
from sqlalchemy import func

admin_revenue_bp = Blueprint('admin_revenue', __name__)
logger = logging.getLogger(__name__)


@admin_revenue_bp.route('/admin/revenue/summary', methods=['GET'])
@require_api_key
def get_revenue_summary():
    """Get summary of platform fees collected (all-time, monthly, weekly)"""
    try:
        # Get all-time totals
        all_time = db.session.query(
            func.sum(StripePlatformRevenue.total_revenue_cents).label('total_revenue'),
            func.sum(StripePlatformRevenue.platform_fee_cents).label('platform_fees')
        ).first()
        
        total_revenue_cents = all_time.total_revenue or 0
        total_platform_fees = all_time.platform_fees or 0
        
        # Get current month totals
        today = date.today()
        month_start = today.replace(day=1)
        
        month_totals = db.session.query(
            func.sum(StripePlatformRevenue.total_revenue_cents).label('total_revenue'),
            func.sum(StripePlatformRevenue.platform_fee_cents).label('platform_fees')
        ).filter(
            StripePlatformRevenue.period_start >= month_start
        ).first()
        
        month_revenue = month_totals.total_revenue or 0
        month_fees = month_totals.platform_fees or 0
        
        # Get last 7 days
        week_ago = today - timedelta(days=7)
        
        week_totals = db.session.query(
            func.sum(StripePlatformRevenue.total_revenue_cents).label('total_revenue'),
            func.sum(StripePlatformRevenue.platform_fee_cents).label('platform_fees')
        ).filter(
            StripePlatformRevenue.period_start >= week_ago
        ).first()
        
        week_revenue = week_totals.total_revenue or 0
        week_fees = week_totals.platform_fees or 0
        
        # Get active subscription count
        active_subscriptions = StripeSubscription.query.filter_by(status='active').count()
        
        # Calculate average subscription value
        if active_subscriptions > 0:
            # Get all active subscriptions and their prices
            active_subs = StripeSubscription.query.filter_by(status='active').all()
            total_value = 0
            
            for sub in active_subs:
                # This is simplified - in a real scenario, we'd need to fetch the price
                # from the subscription's price_id. For now, we'll estimate from monthly revenue
                pass
            
            avg_subscription = month_revenue / active_subscriptions if month_revenue > 0 else 0
        else:
            avg_subscription = 0
        
        return jsonify({
            'all_time': {
                'total_revenue_cents': total_revenue_cents,
                'total_revenue_display': f"${total_revenue_cents / 100:.2f}",
                'platform_fees_cents': total_platform_fees,
                'platform_fees_display': f"${total_platform_fees / 100:.2f}",
                'platform_fee_percent': PLATFORM_FEE_PERCENT
            },
            'current_month': {
                'total_revenue_cents': month_revenue,
                'total_revenue_display': f"${month_revenue / 100:.2f}",
                'platform_fees_cents': month_fees,
                'platform_fees_display': f"${month_fees / 100:.2f}",
                'month': month_start.strftime('%B %Y')
            },
            'last_7_days': {
                'total_revenue_cents': week_revenue,
                'total_revenue_display': f"${week_revenue / 100:.2f}",
                'platform_fees_cents': week_fees,
                'platform_fees_display': f"${week_fees / 100:.2f}"
            },
            'subscriptions': {
                'active_count': active_subscriptions,
                'average_value_cents': int(avg_subscription),
                'average_value_display': f"${avg_subscription / 100:.2f}"
            }
        })
        
    except Exception as e:
        logger.exception("Error in get_revenue_summary")
        return jsonify({'error': str(e)}), 500


@admin_revenue_bp.route('/admin/revenue/breakdown', methods=['GET'])
@require_api_key
def get_revenue_breakdown():
    """Get revenue breakdown by period"""
    try:
        # Get query parameters
        period = request.args.get('period', 'monthly')  # monthly, weekly, yearly
        limit = int(request.args.get('limit', 12))  # Default to last 12 periods
        
        if period == 'monthly':
            # Get monthly breakdown
            records = StripePlatformRevenue.query.order_by(
                StripePlatformRevenue.period_start.desc()
            ).limit(limit).all()
            
            breakdown = []
            for record in records:
                breakdown.append({
                    'period': record.period_start.strftime('%B %Y'),
                    'period_start': record.period_start.isoformat(),
                    'period_end': record.period_end.isoformat(),
                    'total_revenue_cents': record.total_revenue_cents,
                    'total_revenue_display': f"${record.total_revenue_cents / 100:.2f}",
                    'platform_fees_cents': record.platform_fee_cents,
                    'platform_fees_display': f"${record.platform_fee_cents / 100:.2f}",
                    'subscription_count': record.subscription_count
                })
            
            # Reverse to show oldest first
            breakdown.reverse()
            
            return jsonify({
                'period_type': 'monthly',
                'breakdown': breakdown,
                'count': len(breakdown)
            })
        
        elif period == 'yearly':
            # Get yearly aggregation
            yearly_data = db.session.query(
                func.extract('year', StripePlatformRevenue.period_start).label('year'),
                func.sum(StripePlatformRevenue.total_revenue_cents).label('total_revenue'),
                func.sum(StripePlatformRevenue.platform_fee_cents).label('platform_fees'),
                func.avg(StripePlatformRevenue.subscription_count).label('avg_subscriptions')
            ).group_by('year').order_by('year').all()
            
            breakdown = []
            for row in yearly_data:
                breakdown.append({
                    'period': str(int(row.year)),
                    'total_revenue_cents': int(row.total_revenue or 0),
                    'total_revenue_display': f"${(row.total_revenue or 0) / 100:.2f}",
                    'platform_fees_cents': int(row.platform_fees or 0),
                    'platform_fees_display': f"${(row.platform_fees or 0) / 100:.2f}",
                    'avg_subscription_count': int(row.avg_subscriptions or 0)
                })
            
            return jsonify({
                'period_type': 'yearly',
                'breakdown': breakdown,
                'count': len(breakdown)
            })
        
        else:
            return jsonify({'error': 'Invalid period type. Use: monthly, yearly'}), 400
        
    except Exception as e:
        logger.exception("Error in get_revenue_breakdown")
        return jsonify({'error': str(e)}), 500


@admin_revenue_bp.route('/admin/revenue/calculate', methods=['POST'])
@require_api_key
def calculate_revenue():
    """Calculate and cache revenue for a specific date range"""
    try:
        data = request.get_json() or {}
        
        period_start_str = data.get('period_start')
        period_end_str = data.get('period_end')
        
        if not period_start_str or not period_end_str:
            return jsonify({'error': 'period_start and period_end are required (YYYY-MM-DD format)'}), 400
        
        try:
            period_start = datetime.strptime(period_start_str, '%Y-%m-%d').date()
            period_end = datetime.strptime(period_end_str, '%Y-%m-%d').date()
        except ValueError:
            return jsonify({'error': 'Invalid date format. Use YYYY-MM-DD'}), 400
        
        if period_start >= period_end:
            return jsonify({'error': 'period_start must be before period_end'}), 400
        
        # Check if record already exists
        existing = StripePlatformRevenue.query.filter_by(
            period_start=period_start,
            period_end=period_end
        ).first()
        
        if existing:
            return jsonify({
                'message': 'Revenue record already exists for this period',
                'record': existing.to_dict()
            })
        
        # Get active subscriptions in this period
        active_subs = StripeSubscription.query.filter(
            StripeSubscription.created_at <= datetime.combine(period_end, datetime.max.time()),
            StripeSubscription.status == 'active'
        ).count()
        
        # Create new revenue record
        # Note: This is a placeholder. In production, you'd calculate actual revenue
        # from Stripe invoices or other sources
        new_record = StripePlatformRevenue(
            period_start=period_start,
            period_end=period_end,
            total_revenue_cents=0,  # To be updated by webhooks
            platform_fee_cents=0,   # To be updated by webhooks
            subscription_count=active_subs
        )
        
        db.session.add(new_record)
        db.session.commit()
        
        return jsonify({
            'message': 'Revenue record created',
            'record': new_record.to_dict()
        }), 201
        
    except Exception as e:
        logger.exception("Error in calculate_revenue")
        return jsonify({'error': str(e)}), 500


@admin_revenue_bp.route('/admin/revenue/current-period', methods=['GET'])
@require_api_key
def get_current_period_revenue():
    """Get revenue for the current billing period (month)"""
    try:
        today = date.today()
        period_start = today.replace(day=1)
        
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
            # Create placeholder record
            revenue_record = StripePlatformRevenue(
                period_start=period_start,
                period_end=period_end,
                total_revenue_cents=0,
                platform_fee_cents=0,
                subscription_count=StripeSubscription.query.filter_by(status='active').count()
            )
            db.session.add(revenue_record)
            db.session.commit()
        
        return jsonify({
            'current_period': revenue_record.to_dict(),
            'is_current_month': True,
            'days_remaining': (period_end - today).days
        })
        
    except Exception as e:
        logger.exception("Error in get_current_period_revenue")
        return jsonify({'error': str(e)}), 500


@admin_revenue_bp.route('/admin/revenue/trends', methods=['GET'])
@require_api_key
def get_revenue_trends():
    """Get revenue trends for charts"""
    try:
        months = int(request.args.get('months', 6))  # Default to last 6 months
        
        # Get last N months of data
        records = StripePlatformRevenue.query.order_by(
            StripePlatformRevenue.period_start.desc()
        ).limit(months).all()
        
        records.reverse()  # Oldest first for chart display
        
        trends = {
            'labels': [],
            'total_revenue': [],
            'platform_fees': [],
            'subscription_counts': []
        }
        
        for record in records:
            trends['labels'].append(record.period_start.strftime('%b %Y'))
            trends['total_revenue'].append(record.total_revenue_cents / 100)  # Convert to dollars
            trends['platform_fees'].append(record.platform_fee_cents / 100)
            trends['subscription_counts'].append(record.subscription_count)
        
        # Calculate growth
        if len(trends['platform_fees']) >= 2:
            current = trends['platform_fees'][-1]
            previous = trends['platform_fees'][-2]
            
            if previous > 0:
                growth_percent = ((current - previous) / previous) * 100
            else:
                growth_percent = 100 if current > 0 else 0
        else:
            growth_percent = 0
        
        return jsonify({
            'trends': trends,
            'growth_percent': round(growth_percent, 2),
            'months_displayed': len(records)
        })
        
    except Exception as e:
        logger.exception("Error in get_revenue_trends")
        return jsonify({'error': str(e)}), 500

