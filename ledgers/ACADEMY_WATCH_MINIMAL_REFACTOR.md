# The Academy Watch - Minimal Refactor Plan

> Preserve existing components. Adapt, don't rebuild.

---

## Philosophy

**Keep:** Existing UI components, color scheme, patterns, infrastructure
**Change:** Data model expansion, feature additions, branding text
**Remove:** Only what's truly blocking (Stripe complexity, writer recruitment)

---

## What We Keep (90% of the codebase)

### Frontend - Keep As-Is
| Component | Reuse For |
|-----------|-----------|
| `PlayerPage.jsx` | Academy + loan player profiles (already works) |
| `BlockRenderer.jsx` | Newsletter content rendering |
| `CommentaryCard.jsx` | Display community takes |
| `CommentaryEditor.jsx` | Editor's take input |
| `MatchDetailDrawer.jsx` | Fixture details |
| `GlobalSearchDialog.jsx` | Search players/newsletters |
| `NewsletterWriterOverlay.jsx` | Newsletter preview |
| All `/components/ui/*` | Full Shadcn library |
| All `/components/charts/*` | Stats visualization |
| `AuthModal.jsx` | Email OTP login (already built!) |
| `AdminLayout.jsx` | Admin dashboard structure |

### Backend - Keep As-Is
| Component | Notes |
|-----------|-------|
| API-Football sync | Core data pipeline |
| Newsletter generation | Works, just needs content tweaks |
| Email delivery (Mailgun) | Keep |
| User auth (OTP) | Already does magic link style |
| Reddit posting | Keep |
| Stats aggregation | Keep |
| All existing models | Keep, extend `LoanedPlayer` |

---

## Minimal Changes Required

### Phase 1: Simplify (Remove Blockers)

#### 1.1 Remove Stripe (Backend)
**Why:** Complexity we're not using
**Files to delete:**
```
src/routes/stripe_journalist.py
src/routes/stripe_subscriber.py
src/routes/stripe_webhooks.py
```
**In `main.py`:** Remove blueprint registrations
**Time:** ~1 hour

#### 1.2 Remove Stripe (Frontend)
**Files to delete:**
```
src/pages/JournalistPricing.jsx
src/pages/JournalistStripeSetup.jsx
src/context/StripeContext.jsx
```
**In `App.jsx`:** Remove routes + context provider
**Time:** ~30 min

#### 1.3 Simplify Writer System → Editor System
**Don't delete** `WriterDashboard.jsx` or `WriteupEditor.jsx` — **adapt them**:
- Remove coverage request UI
- Remove team assignment complexity
- Single editor mode (you)

**Files to simplify:**
```
src/pages/writer/WriterDashboard.jsx  → Remove coverage requests section
src/pages/admin/AdminUsers.jsx        → Simplify role management
```
**Time:** ~2 hours

---

### Phase 2: Extend Data Model

#### 2.1 Extend LoanedPlayer (Don't Rename Yet)
Add columns to existing model:
```python
# In models/league.py, add to LoanedPlayer:
pathway_status = db.Column(db.String(20), default='on_loan')
# Values: 'academy' | 'on_loan' | 'first_team' | 'released'

current_level = db.Column(db.String(20), nullable=True)
# Values: 'U18' | 'U21' | 'U23' | 'Senior'

data_depth = db.Column(db.String(20), default='full_stats')
# Values: 'full_stats' | 'events_only' | 'profile_only'
```
**Migration:** Add columns, set defaults for existing rows
**Time:** ~30 min

#### 2.2 Add CommunityTake Model
New model for aggregated takes:
```python
class CommunityTake(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    source_type = db.Column(db.String(20))  # 'reddit' | 'submission' | 'editor'
    source_author = db.Column(db.String(100))
    source_url = db.Column(db.String(500), nullable=True)
    content = db.Column(db.Text)
    player_id = db.Column(db.Integer, db.ForeignKey('player.id'), nullable=True)
    status = db.Column(db.String(20), default='pending')  # 'pending' | 'approved'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
```
**Time:** ~30 min

---

### Phase 3: Add Community Features

#### 3.1 Quick Take Submission API
New route file: `src/routes/community.py`
```python
POST /api/community-takes/submit    # Public (requires email)
GET  /api/community-takes           # List approved takes
GET  /api/admin/community-takes     # Curation queue
POST /api/admin/community-takes/:id/approve
POST /api/admin/community-takes/:id/reject
```
**Time:** ~2 hours

#### 3.2 Quick Take Submission Form (Frontend)
**Reuse existing patterns:**
- Use `AuthModal.jsx` pattern for email verification
- Use `CommentaryEditor.jsx` as base for take input
- Use existing `Card`, `Button`, `Input` from ui/

**New file:** `src/pages/SubmitTake.jsx` (~200 lines)
**Time:** ~3 hours

#### 3.3 Curation Dashboard (Frontend)
**Reuse existing patterns:**
- Use `AdminLayout.jsx` wrapper
- Use `Card`, `Badge`, `Button` from ui/
- Pattern similar to `AdminNewsletters.jsx` (list + actions)

**New file:** `src/pages/admin/AdminCuration.jsx` (~300 lines)
**Time:** ~3 hours

#### 3.4 Integrate Takes into Newsletter
**Modify** `NewsletterWriterOverlay.jsx`:
- Add "Community Takes" section per player
- Fetch approved takes for each player

**Time:** ~2 hours

---

### Phase 4: Reddit Scraper

#### 4.1 Reddit Scraper Service
**New file:** `src/services/reddit_scraper.py`
- Use PRAW library
- Search subreddits for player mentions
- Create pending CommunityTakes

**Time:** ~4 hours

#### 4.2 Admin Trigger
Add to `AdminCuration.jsx`:
- "Scrape r/reddevils" button
- Shows scraped content in queue

**Time:** ~1 hour

---

### Phase 5: Branding Update

#### 5.1 Text Changes Only
Find & replace in frontend:
- "Go On Loan" → "The Academy Watch"
- Update `<title>` in `index.html`
- Update email templates

**Keep:** Existing black/white color scheme (Athletic-inspired already!)
**Time:** ~1 hour

---

## Implementation Order

```
Week 1: Phase 1 (Simplify)
├── Remove Stripe
├── Simplify writer flows
└── Test everything still works

Week 2: Phase 2 (Data Model)
├── Extend LoanedPlayer
├── Add CommunityTake model
└── Migrations

Week 3: Phase 3 (Community Features)
├── Submission API + form
├── Curation dashboard
└── Newsletter integration

Week 4: Phase 4 + 5 (Reddit + Branding)
├── Reddit scraper
├── Branding updates
└── Final testing
```

---

## Component Reuse Map

| New Feature | Existing Component to Adapt |
|-------------|----------------------------|
| Quick take form | `CommentaryEditor.jsx` + `AuthModal.jsx` patterns |
| Curation dashboard | `AdminNewsletters.jsx` patterns |
| Community takes display | `CommentaryCard.jsx` |
| Player pathway timeline | New, but use existing `Card` + `Badge` |
| Reddit import | `AdminReddit.jsx` patterns (already exists!) |

---

## What NOT To Do

1. ❌ Don't redesign the UI - it works
2. ❌ Don't rename `LoanedPlayer` to `TrackedPlayer` yet - adds migration risk
3. ❌ Don't remove writer system entirely - simplify it
4. ❌ Don't rebuild newsletter generation - add to it
5. ❌ Don't change the color scheme - keep Athletic-inspired black/white

---

## Files Changed Summary

### Delete (5 files)
```
src/routes/stripe_journalist.py
src/routes/stripe_subscriber.py
src/routes/stripe_webhooks.py
src/pages/JournalistPricing.jsx
src/pages/JournalistStripeSetup.jsx
```

### New (4 files)
```
src/routes/community.py           # Community takes API
src/services/reddit_scraper.py    # Reddit integration
src/pages/SubmitTake.jsx          # Public submission form
src/pages/admin/AdminCuration.jsx # Curation dashboard
```

### Modify (8 files)
```
src/models/league.py              # Add columns + CommunityTake model
src/main.py                       # Register new routes, remove Stripe
src/App.jsx                       # Add routes, remove Stripe context
src/pages/writer/WriterDashboard.jsx    # Simplify
src/components/NewsletterWriterOverlay.jsx  # Add community takes
src/pages/admin/AdminDashboard.jsx      # Add curation stats
index.html                        # Title change
Email templates                   # Branding
```

---

## Success Criteria

- [ ] App runs without Stripe
- [ ] Editor can write commentary (simplified flow)
- [ ] Users can submit takes via email auth
- [ ] Admin can approve/reject takes
- [ ] Newsletter shows community takes
- [ ] Reddit scraping works
- [ ] Branding says "The Academy Watch"
