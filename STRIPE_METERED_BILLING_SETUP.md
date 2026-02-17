# Stripe Metered Billing Setup - Pay Per Newsletter

## Overview

This system charges subscribers **only when newsletters are published**, not as a fixed monthly fee. Subscribers pay:

```
Monthly Bill = (Price per Newsletter) × (Newsletters Published This Month)
```

- Journalist sets price per newsletter (e.g., $2.99 per newsletter)
- Subscriber signs up for a "subscription"
- Each time journalist publishes a newsletter, we record usage in Stripe
- At end of billing period, Stripe charges: (# of newsletters) × (price per newsletter)
- The Academy Watch automatically gets 10% via application fee

## How It Works

### 1. Journalist Sets Price

When a journalist sets their price at `/journalist/pricing`:
- They set **price per newsletter** (e.g., $3.99)
- Stripe creates a **metered billing price**
- Price has `usage_type: 'metered'`

### 2. Subscriber Signs Up

When a subscriber subscribes:
- They provide payment method
- Stripe creates a subscription (but doesn't charge yet)
- Subscription status is "active" with $0 initial charge

### 3. Newsletter Published

When a journalist publishes a newsletter:
- Your system calls: `POST /api/newsletters/{id}/record-publication`
- This records "1 unit of usage" for all subscribers
- Stripe tracks this usage for the billing period

### 4. End of Billing Period

At the end of each month:
- Stripe automatically sums up usage (# of newsletters)
- Calculates charge: (newsletters published) × (price per newsletter)
- Charges the subscriber
- Automatically sends 90% to journalist, 10% to platform

## Example Scenario

**Journalist Setup:**
- Sets price: $4.99 per newsletter
- Has 50 subscribers

**Month Activity:**
- Week 1: Publishes newsletter → 50 subscribers each get 1 usage recorded
- Week 2: Publishes newsletter → 50 subscribers each get 1 usage recorded (total: 2)
- Week 3: No newsletter
- Week 4: Publishes newsletter → 50 subscribers each get 1 usage recorded (total: 3)

**End of Month Billing:**
- Each subscriber is charged: 3 newsletters × $4.99 = $14.97
- Journalist receives: $14.97 × 0.90 = $13.47 per subscriber × 50 = $673.50
- Platform receives: $14.97 × 0.10 = $1.50 per subscriber × 50 = $75.00

**Next Month:**
- Usage resets to 0
- Process repeats

## Setting Up in Stripe Sandbox

### 1. Configure Your Stripe Account

Your "The Academy Watch" business account in Stripe is the **Platform Account**.

### 2. Test the Flow

#### A. Create Journalist Account
```bash
# As admin, mark user as journalist
curl -X POST http://localhost:5001/api/stripe/journalist/onboard \
  -H "Content-Type: application/json" \
  --cookie "session=your_session"
```

#### B. Set Price Per Newsletter
```bash
# Set $3.99 per newsletter
curl -X POST http://localhost:5001/api/stripe/journalist/create-price \
  -H "Content-Type: application/json" \
  --cookie "session=your_session" \
  -d '{"price": 3.99}'
```

This creates a Stripe price with:
```json
{
  "unit_amount": 399,
  "currency": "usd",
  "recurring": {
    "interval": "month",
    "usage_type": "metered",
    "aggregate_usage": "sum"
  }
}
```

#### C. Subscriber Signs Up
```bash
# Subscriber subscribes to journalist
curl -X POST http://localhost:5001/api/stripe/subscribe/123 \
  -H "Content-Type: application/json" \
  --cookie "session=subscriber_session"
```

Subscriber sees Stripe Checkout for $0.00 initial charge with message:
"You'll be charged $3.99 per newsletter published"

#### D. Record Newsletter Publication
```bash
# When newsletter is published
curl -X POST http://localhost:5001/api/newsletters/456/record-publication \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your_admin_api_key" \
  -d '{"journalist_user_id": 123}'
```

This records 1 usage unit for all subscribers.

#### E. Check Usage
```bash
# See how many newsletters subscriber has been charged for this period
curl "http://localhost:5001/api/subscribers/usage?subscriber_user_id=789&journalist_user_id=123"
```

Response:
```json
{
  "current_period_usage": 3,
  "current_period_start": "2024-11-01",
  "current_period_end": "2024-12-01"
}
```

### 3. Verify in Stripe Dashboard

1. Go to https://dashboard.stripe.com/test/subscriptions
2. Find the subscription
3. Click on it
4. See "Usage" tab showing newsletters recorded
5. At end of billing period, see invoice for (usage × price)

## Key Differences from Monthly Subscriptions

| Monthly Subscription | Metered (Pay per Newsletter) |
|---------------------|----------------------------|
| Fixed $9.99/month | Variable based on usage |
| Charged on signup | First charge after first newsletter |
| Same bill every month | Changes based on publications |
| Subscriber knows exact cost | Subscriber sees variable bills |
| No usage tracking needed | Must record each newsletter |

## Integration Points

### 1. Newsletter Publish Hook

Add to your newsletter publishing code:

```python
from src.services.stripe_usage_service import record_newsletter_publication

# When newsletter is published
if newsletter.published and journalist_id:
    result = record_newsletter_publication(
        journalist_user_id=journalist_id,
        newsletter_id=newsletter.id,
        quantity=1
    )
    logger.info(f"Recorded usage for {result['success']} subscribers")
```

### 2. Frontend Display

Update subscription display to show:
- Price per newsletter (not per month)
- Current period usage: "You've been charged for 3 newsletters this month"
- Estimated next bill: "Estimated: $11.97 (3 newsletters × $3.99)"

### 3. Pricing Page Updates

Change journalist pricing page to clarify:
- "Price per newsletter" instead of "Monthly price"
- Example: "If you publish 4 newsletters this month, subscribers pay $15.96"

## Testing in Stripe Sandbox

### Test Scenario 1: Basic Usage

```bash
# 1. Create subscription (test card 4242 4242 4242 4242)
# 2. Verify $0.00 initial charge
# 3. Publish 2 newsletters (record usage twice)
# 4. Wait for billing period end OR manually create invoice
stripe invoices create \
  --customer cus_xxx \
  --subscription sub_xxx \
  --auto-advance true
```

### Test Scenario 2: No Newsletters Published

- Subscriber subscribes
- No newsletters published all month
- At end of period: **$0.00 charge** (no usage)

### Test Scenario 3: Many Newsletters

- Journalist publishes 10 newsletters
- Each subscriber charged: 10 × price per newsletter
- Platform gets 10% of total

## Stripe CLI Commands

```bash
# List usage records
stripe subscription_items list_usage_record_summaries si_xxx

# Manually record usage (for testing)
stripe subscription_items create_usage_record si_xxx \
  --quantity 1 \
  --timestamp now

# Trigger billing period end (for testing)
stripe subscriptions update sub_xxx \
  --billing_cycle_anchor now
```

## Pricing Considerations

### Journalist Guidance

Suggest pricing based on publication frequency:

| Frequency | Suggested Price | Monthly Revenue (if consistent) |
|-----------|----------------|--------------------------------|
| 1/week (4/month) | $3.99/newsletter | ~$16/month per subscriber |
| 2/week (8/month) | $2.49/newsletter | ~$20/month per subscriber |
| 3/week (12/month) | $1.99/newsletter | ~$24/month per subscriber |
| Daily (30/month) | $0.99/newsletter | ~$30/month per subscriber |

### Subscriber Benefits

- Only pay when value is delivered (newsletter published)
- No charge if journalist takes a break
- Fair pricing based on actual content received

## Important Notes

1. **First charge after first newsletter** - Subscribers won't be charged until first newsletter publishes
2. **Usage resets monthly** - Each billing period starts fresh
3. **Can't unpublish** - Once usage is recorded, it can't be removed (Stripe limitation)
4. **Minimum billing** - Consider adding minimum monthly fee if needed
5. **Preview bills** - Subscribers can see upcoming invoice in Stripe portal

## Advantages of This Model

✅ **Fair to subscribers** - Only pay for content received
✅ **Encourages quality** - Journalists incentivized to publish regularly
✅ **Flexible** - Works for any publication frequency
✅ **Transparent** - Clear what each newsletter costs
✅ **Platform friendly** - 10% on actual revenue, not potential

## Monitoring

Check these metrics in admin dashboard:
- Total usage units recorded (all newsletters published)
- Average newsletters per journalist per month
- Average subscriber bill amount
- Platform revenue per newsletter published

## Go Live Checklist

- [ ] Test full flow in sandbox
- [ ] Verify usage recording works
- [ ] Check invoices generate correctly
- [ ] Test with different publication frequencies
- [ ] Update all UI text to "per newsletter" instead of "per month"
- [ ] Add usage display to subscriber dashboard
- [ ] Switch to live Stripe keys
- [ ] Monitor first real billing period

---

**Ready to test?** Follow the Quick Start to set up your sandbox environment!

