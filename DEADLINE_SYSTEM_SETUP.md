# Newsletter Deadline System - Monday 23:59 GMT

## Overview

The deadline system ensures:
1. **Writers have until Monday 23:59 GMT** to submit their content
2. **At the deadline**, system automatically publishes newsletters
3. **Only writers who submitted content** get their subscribers charged
4. **Subscribers receive emails** with their subscribed writers' content

## How It Works

### Timeline

```
Week Flow:
Monday 00:00 GMT    → New week starts, writers begin work
  ↓
Friday              → Writers writing content
  ↓
Monday 23:59 GMT    → DEADLINE! System auto-processes:
                      1. Check which writers submitted content
                      2. Publish newsletter
                      3. Charge only subscribers of writers who submitted
                      4. Send emails to subscribers
  ↓
Tuesday             → New week begins
```

### What Happens at Deadline

**Monday 23:59 GMT, system automatically:**

1. **Finds newsletters** for the week that just ended
2. **Checks each writer** - did they submit publishable content?
3. **Publishes newsletter** (if at least one writer submitted)
4. **Records usage** (charges) ONLY for writers who submitted
5. **Sends emails** to subscribers with their writers' content

### Writer Scenarios

**Scenario A: Writer Submits Content**
```
Writer submits 500 words by Monday 23:00 GMT
→ Content detected ✓
→ Newsletter publishes ✓
→ Their subscribers charged ✓
→ Subscribers receive email ✓
```

**Scenario B: Writer Doesn't Submit**
```
Writer doesn't submit by Monday 23:59 GMT
→ No content detected ✗
→ Newsletter still publishes (if others submitted) ✓
→ Their subscribers NOT charged ✗
→ Subscribers don't receive email ✗
```

**Scenario C: Multiple Writers, Mixed Submissions**
```
Newsletter for Team X:
- Writer A: Submitted content ✓ → Their subscribers charged
- Writer B: No content ✗ → Their subscribers NOT charged

Result: Newsletter publishes with Writer A's content only
```

## API Endpoints

### 1. Check Deadline Info

Get when the next deadline is:

```bash
GET /api/newsletters/deadline/info
```

Response:
```json
{
  "next_deadline": "2024-12-02T23:59:59.999999+00:00",
  "time_remaining_hours": 48.5,
  "time_remaining_formatted": "2 days, 30 minutes",
  "week_start_date": "2024-11-25",
  "current_time_utc": "2024-11-30T23:30:00+00:00"
}
```

### 2. Check Writer Submission Status

Writer checks if they've submitted:

```bash
GET /api/writers/submission-status
Authorization: Bearer <token>
```

Response:
```json
{
  "journalist_id": 123,
  "journalist_name": "John Smith",
  "week_start_date": "2024-11-25",
  "newsletters": [
    {
      "newsletter_id": 456,
      "team_id": 33,
      "has_submitted": true,
      "published": false
    }
  ],
  "deadline": {
    "next_deadline": "2024-12-02T23:59:59+00:00",
    "time_remaining_formatted": "1 hour, 30 minutes"
  },
  "all_submitted": true
}
```

### 3. Process Deadline (Automatic/Admin)

Triggered automatically at Monday 23:59 GMT:

```bash
POST /api/newsletters/deadline/process
X-API-Key: admin_key

# Optional: specify week for testing
{
  "week_start_date": "2024-11-25"
}
```

Response:
```json
{
  "message": "Deadline processed",
  "result": {
    "newsletters_processed": 3,
    "writers_charged": 5,
    "subscribers_notified": 127,
    "details": [
      {
        "newsletter_id": 456,
        "team_id": 33,
        "published": true,
        "writers_charged": 2,
        "writers_without_content": 1,
        "subscribers_notified": 45,
        "writer_names": ["John Smith", "Jane Doe"]
      }
    ]
  }
}
```

### 4. Test Deadline Processing

Test the system without waiting for Monday:

```bash
POST /api/newsletters/deadline/test
X-API-Key: admin_key

{
  "week_start_date": "2024-11-25"
}
```

## Setting Up Automatic Execution

### Option 1: Cron Job (Linux/Unix)

Add to crontab to run every Monday at 23:59 GMT:

```bash
# Edit crontab
crontab -e

# Add this line (runs at 23:59 every Monday)
59 23 * * 1 curl -X POST https://your-api.com/api/newsletters/deadline/process \
  -H "X-API-Key: your_admin_key" \
  >> /var/log/newsletter-deadline.log 2>&1
```

### Option 2: GitHub Actions (Free)

Create `.github/workflows/newsletter-deadline.yml`:

```yaml
name: Newsletter Deadline Processing

on:
  schedule:
    # Runs at 23:59 UTC every Monday
    - cron: '59 23 * * 1'
  workflow_dispatch:  # Allow manual trigger

jobs:
  process-deadline:
    runs-on: ubuntu-latest
    steps:
      - name: Trigger deadline processing
        run: |
          curl -X POST ${{ secrets.API_URL }}/api/newsletters/deadline/process \
            -H "X-API-Key: ${{ secrets.ADMIN_API_KEY }}" \
            -H "Content-Type: application/json"
```

### Option 3: Cloud Scheduler (Azure/AWS/GCP)

**Azure Functions (Timer Trigger):**
```python
import azure.functions as func
import requests

def main(mytimer: func.TimerRequest):
    # Runs every Monday at 23:59 GMT
    response = requests.post(
        'https://your-api.com/api/newsletters/deadline/process',
        headers={'X-API-Key': 'your_admin_key'}
    )
    return response.json()
```

**AWS Lambda + EventBridge:**
```
Schedule expression: cron(59 23 ? * MON *)
Time zone: GMT
```

### Option 4: Python Background Worker

```python
# deadline_worker.py
import schedule
import time
import requests
from datetime import datetime
import pytz

def process_deadline():
    """Run at Monday 23:59 GMT"""
    print(f"Processing deadline at {datetime.now(pytz.UTC)}")
    
    response = requests.post(
        'http://localhost:5001/api/newsletters/deadline/process',
        headers={'X-API-Key': 'your_admin_key'}
    )
    
    print(f"Result: {response.json()}")

# Schedule for Monday 23:59 GMT
schedule.every().monday.at("23:59").do(process_deadline)

print("Deadline worker started. Waiting for Monday 23:59 GMT...")

while True:
    schedule.run_pending()
    time.sleep(60)  # Check every minute
```

Run with:
```bash
TZ=GMT python deadline_worker.py
```

## Writer Dashboard Integration

### Display Deadline Countdown

```javascript
// Frontend component
function DeadlineCountdown({ journalist }) {
  const [deadline, setDeadline] = useState(null);
  const [timeRemaining, setTimeRemaining] = useState('');

  useEffect(() => {
    // Fetch deadline info
    fetch('/api/newsletters/deadline/info')
      .then(r => r.json())
      .then(data => {
        setDeadline(data.next_deadline);
        setTimeRemaining(data.time_remaining_formatted);
      });
  }, []);

  return (
    <div className="deadline-banner">
      <h3>⏰ Submission Deadline</h3>
      <p>Monday 23:59 GMT</p>
      <p className="countdown">{timeRemaining} remaining</p>
    </div>
  );
}
```

### Show Submission Status

```javascript
function SubmissionStatus({ journalist }) {
  const [status, setStatus] = useState(null);

  useEffect(() => {
    fetch('/api/writers/submission-status', {
      credentials: 'include'
    })
      .then(r => r.json())
      .then(setStatus);
  }, []);

  if (!status) return <div>Loading...</div>;

  return (
    <div className="submission-status">
      <h3>This Week's Submissions</h3>
      {status.newsletters.map(newsletter => (
        <div key={newsletter.newsletter_id}>
          <span>Team {newsletter.team_id}</span>
          {newsletter.has_submitted ? (
            <span className="badge success">✓ Submitted</span>
          ) : (
            <span className="badge warning">⚠ Not submitted</span>
          )}
        </div>
      ))}
      
      {!status.all_submitted && (
        <div className="alert">
          ⚠️ You have {status.newsletters.filter(n => !n.has_submitted).length} 
          newsletters pending. Submit before Monday 23:59 GMT to charge your subscribers.
        </div>
      )}
    </div>
  );
}
```

## Email Integration

After deadline processing, integrate with your email system:

```python
# In newsletter_deadline_service.py, add after publishing:

def send_subscriber_emails(newsletter_id, writers_with_content):
    """Send emails to subscribers with their writers' content"""
    
    for writer in writers_with_content:
        # Get writer's subscribers
        subscriptions = StripeSubscription.query.filter_by(
            journalist_user_id=writer.id,
            status='active'
        ).all()
        
        for sub in subscriptions:
            subscriber = UserAccount.query.get(sub.subscriber_user_id)
            
            # Send email with writer's content
            send_email(
                to=subscriber.email,
                subject=f"New content from {writer.display_name}",
                body=render_newsletter_email(
                    newsletter_id=newsletter_id,
                    writer_id=writer.id
                )
            )
```

## Testing the System

### Test 1: Writer Submits on Time

```bash
# 1. Create newsletter for this week
# 2. Writer adds content
# 3. Run deadline processing
curl -X POST http://localhost:5001/api/newsletters/deadline/test \
  -H "X-API-Key: admin_key" \
  -H "Content-Type: application/json"

# 4. Check result - writer's subscribers should be charged
```

### Test 2: Writer Misses Deadline

```bash
# 1. Create newsletter for this week
# 2. Writer doesn't add content (or adds too little)
# 3. Run deadline processing
# 4. Check result - writer's subscribers NOT charged
```

### Test 3: Multiple Writers

```bash
# 1. Create newsletter with 3 writers
# 2. Writer A submits content
# 3. Writer B submits content
# 4. Writer C doesn't submit
# 5. Run deadline processing
# Result: 
#   - Newsletter publishes
#   - Writer A's subscribers charged
#   - Writer B's subscribers charged
#   - Writer C's subscribers NOT charged
```

## Monitoring

### Log What to Watch

The system logs:
- ✅ Which writers submitted content
- ❌ Which writers missed deadline
- 💰 How many subscribers charged per writer
- 📧 How many emails sent

### Example Log Output

```
2024-12-02 23:59:00 INFO: Processing newsletter deadline for week starting 2024-11-25
2024-12-02 23:59:01 INFO: Found 3 unpublished newsletters
2024-12-02 23:59:02 INFO: Newsletter 456 - Writer John Smith: content found ✓
2024-12-02 23:59:02 INFO: Newsletter 456 - Writer Jane Doe: content found ✓
2024-12-02 23:59:02 INFO: Newsletter 456 - Writer Bob Wilson: no content ✗
2024-12-02 23:59:03 INFO: Published newsletter 456 with content from 2 writers
2024-12-02 23:59:04 INFO: Recorded usage for writer John Smith: 35 subscribers charged
2024-12-02 23:59:05 INFO: Recorded usage for writer Jane Doe: 28 subscribers charged
2024-12-02 23:59:05 INFO: Writer Bob Wilson did not submit - their 12 subscribers NOT charged
2024-12-02 23:59:06 INFO: Deadline processing complete: 3 newsletters, 5 writers charged, 127 subscribers
```

## Deadline Rules

### What Counts as "Publishable Content"?

```python
def is_publishable(content):
    # Must exist
    if not content:
        return False
    
    # Must be substantial (at least 50 characters)
    if len(content.strip()) < 50:
        return False
    
    # Add more rules as needed:
    # - Must have certain structure
    # - Must not be placeholder text
    # - etc.
    
    return True
```

### Grace Period?

Currently: **Hard deadline at 23:59 GMT Monday**

To add 1-hour grace period:
```python
# In newsletter_deadline_service.py
deadline = next_monday.replace(hour=23, minute=59) + timedelta(hours=1)
# Now deadline is Tuesday 00:59 GMT
```

## Troubleshooting

**Deadline processing didn't run:**
- Check cron job is active: `crontab -l`
- Check server timezone: `date` (should be GMT)
- Check logs for errors

**Writer submitted but not charged:**
- Check content length (must be ≥50 characters)
- Check `NewsletterCommentary` record exists
- Check `author_id` matches journalist

**Subscribers charged when writer didn't submit:**
- This shouldn't happen - check logs
- Verify usage recording logic
- Check which endpoint was called

## Summary

This deadline system provides:

✅ **Clear deadline** - Writers know they have until Monday 23:59 GMT
✅ **Automatic processing** - No manual intervention needed
✅ **Fair billing** - Only charge when content is delivered
✅ **Status visibility** - Writers see if they've submitted
✅ **Flexible** - Works with any number of writers per newsletter

**Next Steps:**
1. Set up automatic execution (cron/cloud scheduler)
2. Add deadline countdown to writer dashboard
3. Configure email notifications
4. Test with upcoming Monday deadline!

