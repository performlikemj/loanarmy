# The Academy Watch - Refactor Plan

> Epic ledger for transforming "Go On Loan" into "The Academy Watch"
> A non-first-team player tracker with community-sourced commentary

---

## Vision

**From:** Go On Loan - Loan player tracking with recruited writers
**To:** The Academy Watch - Academy + loan player tracking with community-curated takes

### Core Value Proposition

Track the full pathway: **Academy → Loan → First Team**

Fans get:
- Weekly updates on academy and loaned players
- Community takes (curated from Reddit, user submissions)
- Your editorial voice + AI-assisted factual layer

### Key Pivot Points

| Before | After |
|--------|-------|
| Loan players only | Academy + loan players |
| Recruit dedicated writers | Aggregate community voices |
| Complex multi-writer platform | Single editor + community takes |
| AI-generated summaries | AI facts + human commentary |
| "Go On Loan" brand | "The Academy Watch" brand |

---

## Data Reality (API-Football Constraints)

### What's Available for Youth Leagues

| Data Type | Senior/Loan | Academy (U18/U21/U23) |
|-----------|-------------|----------------------|
| Detailed stats (minutes, passes, ratings) | ✅ | ❌ |
| Lineups (who played) | ✅ | ✅ (some leagues) |
| Events (goals, assists, cards) | ✅ | ✅ |
| Fixtures & scores | ✅ | ✅ |
| Player profiles | ✅ | ✅ |

### Coverage: 102 Youth Leagues Including
- England: Professional Development League, U18 Premier League, FA Youth Cup
- Europe: UEFA Youth League, Campionato Primavera, U19 Bundesliga
- International: World Cup U20, UEFA U21 Championship

### Implication for Product
- Academy tracking = appearances + events (goals/cards), NOT detailed stats
- Loan tracking = full stats (existing functionality)
- First team debut = full stats unlock

---

## Feature Mapping: Keep / Cut / Modify / Add

### KEEP (Core Infrastructure)
- [x] API-Football data pipeline
- [x] Newsletter generation system
- [x] Email delivery (Mailgun)
- [x] User authentication (email OTP)
- [x] Fixture and stats tracking
- [x] Reddit posting integration
- [x] Basic subscription management

### CUT (Complexity Reduction)
- [ ] Multi-writer recruitment system
- [ ] Stripe Connect writer payments
- [ ] Complex writer assignment workflows
- [ ] Writer coverage requests
- [ ] Journalist subscription tiers
- [ ] Premium/free content split
- [ ] Editor role managing other writers

### MODIFY (Adapt Existing)
- [ ] `LoanedPlayer` → `TrackedPlayer` (add academy status)
- [ ] Newsletter content structure (add community takes section)
- [ ] Admin dashboard (simplify, add curation tools)
- [ ] Writer interface → Editor interface (single user)
- [ ] Stats display (handle limited academy data gracefully)

### ADD (New Features)
- [ ] Reddit content scraper/aggregator
- [ ] Community quick-take submission form
- [ ] Curation dashboard (approve/reject takes)
- [ ] Academy league tracking (U18, U21, U23)
- [ ] Player status tracking (academy → loan → first team)
- [ ] Community ratings system (optional, phase 2)

---

## Database Schema Changes

### Modified Models

#### TrackedPlayer (formerly LoanedPlayer)
```python
class TrackedPlayer(db.Model):
    # Existing fields kept
    id = db.Column(db.Integer, primary_key=True)
    player_id = db.Column(db.Integer, db.ForeignKey('player.id'))
    primary_team_id = db.Column(db.Integer, db.ForeignKey('team.id'))

    # NEW: Player pathway status
    pathway_status = db.Column(db.String(20), default='academy')
    # Values: 'academy' | 'on_loan' | 'first_team' | 'released'

    # NEW: Current level
    current_level = db.Column(db.String(20))
    # Values: 'U18' | 'U21' | 'U23' | 'Reserve' | 'Senior'

    # NEW: Data availability indicator
    data_depth = db.Column(db.String(20), default='events_only')
    # Values: 'full_stats' | 'events_only' | 'profile_only'

    # Loan-specific (nullable for academy players)
    loan_team_id = db.Column(db.Integer, db.ForeignKey('team.id'), nullable=True)
    loan_start_date = db.Column(db.Date, nullable=True)
    loan_end_date = db.Column(db.Date, nullable=True)

    # Stats (populated when available)
    appearances = db.Column(db.Integer, default=0)
    goals = db.Column(db.Integer, default=0)
    assists = db.Column(db.Integer, default=0)
    minutes_played = db.Column(db.Integer, default=0)
    # ... other stats remain
```

### New Models

#### CommunityTake
```python
class CommunityTake(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    # Source
    source_type = db.Column(db.String(20))  # 'reddit' | 'twitter' | 'submission' | 'editor'
    source_url = db.Column(db.String(500), nullable=True)
    source_author = db.Column(db.String(100))  # Reddit username, Twitter handle, or display name
    source_platform = db.Column(db.String(50), nullable=True)  # 'r/reddevils', '@handle', etc.

    # Content
    content = db.Column(db.Text, nullable=False)  # The actual take (1-3 sentences)

    # Association
    player_id = db.Column(db.Integer, db.ForeignKey('player.id'), nullable=True)
    team_id = db.Column(db.Integer, db.ForeignKey('team.id'), nullable=True)
    newsletter_id = db.Column(db.Integer, db.ForeignKey('newsletter.id'), nullable=True)

    # Curation
    status = db.Column(db.String(20), default='pending')  # 'pending' | 'approved' | 'rejected'
    curated_by = db.Column(db.Integer, db.ForeignKey('user_account.id'), nullable=True)
    curated_at = db.Column(db.DateTime, nullable=True)

    # Metadata
    scraped_at = db.Column(db.DateTime, default=datetime.utcnow)
    original_posted_at = db.Column(db.DateTime, nullable=True)
    upvotes = db.Column(db.Integer, default=0)  # From Reddit/Twitter

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
```

#### QuickTakeSubmission
```python
class QuickTakeSubmission(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    # Submitter (can be anonymous)
    submitter_name = db.Column(db.String(100), nullable=True)
    submitter_email = db.Column(db.String(255), nullable=True)

    # Content
    player_id = db.Column(db.Integer, db.ForeignKey('player.id'))
    content = db.Column(db.Text, nullable=False)  # Max ~280 chars

    # Moderation
    status = db.Column(db.String(20), default='pending')
    reviewed_by = db.Column(db.Integer, db.ForeignKey('user_account.id'), nullable=True)
    reviewed_at = db.Column(db.DateTime, nullable=True)
    rejection_reason = db.Column(db.String(255), nullable=True)

    # If approved, links to CommunityTake
    community_take_id = db.Column(db.Integer, db.ForeignKey('community_take.id'), nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    ip_hash = db.Column(db.String(64), nullable=True)  # For spam prevention
```

#### AcademyLeague
```python
class AcademyLeague(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    api_football_id = db.Column(db.Integer, unique=True)
    name = db.Column(db.String(200))
    country = db.Column(db.String(100))
    level = db.Column(db.String(20))  # 'U18' | 'U21' | 'U23' | 'Reserve'
    parent_league_id = db.Column(db.Integer, db.ForeignKey('league.id'), nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    has_lineups = db.Column(db.Boolean, default=False)
    has_events = db.Column(db.Boolean, default=True)
```

### Models to Remove/Deprecate
- `JournalistTeamAssignment` → Remove
- `JournalistLoanTeamAssignment` → Remove
- `WriterCoverageRequest` → Remove
- `StripeConnectedAccount` → Remove
- `StripeSubscriptionPlan` → Remove
- `StripeSubscription` → Remove
- `StripePlatformRevenue` → Remove
- `JournalistSubscription` → Remove
- `NewsletterCommentary` → Simplify (editor-only, or convert to CommunityTake)

---

## API Changes

### Remove Endpoints (Stripe/Writer Complexity)
```
DELETE /stripe/*                          # All Stripe endpoints
DELETE /journalists/invite                # Writer recruitment
DELETE /journalists/*/assign-teams        # Writer assignments
DELETE /writer/coverage-requests          # Coverage request workflow
DELETE /admin/coverage-requests           # Coverage approval
DELETE /admin/journalists/*/loan-team-assignments
```

### Modify Endpoints
```
GET  /teams/:id/loans     → GET  /teams/:id/players    # Include academy
GET  /loans               → GET  /tracked-players      # Renamed, expanded
POST /newsletters/generate → Include academy data
```

### Add Endpoints
```
# Community Takes
GET    /api/community-takes                 # List curated takes
POST   /api/community-takes/submit          # Public submission form
GET    /api/admin/community-takes           # Admin curation queue
POST   /api/admin/community-takes/:id/approve
POST   /api/admin/community-takes/:id/reject

# Reddit Scraping
POST   /api/admin/reddit/scrape/:subreddit  # Trigger scrape
GET    /api/admin/reddit/scraped            # View scraped content

# Academy
GET    /api/academy-leagues                 # List tracked youth leagues
GET    /api/teams/:id/academy               # Academy players for team
POST   /api/admin/academy/sync              # Sync academy data
```

---

## Frontend Changes

### Pages to Remove
- `JournalistPricing.jsx` → Delete
- `JournalistStripeSetup.jsx` → Delete
- `AdminCoverageRequests.jsx` → Delete
- `AdminExternalWriters.jsx` → Delete (or heavily simplify)
- `AdminRevenueDashboard.jsx` → Delete

### Pages to Modify
- `AdminDashboard.jsx` → Simplify, add curation stats
- `AdminNewsletters.jsx` → Add community takes section
- `WriterDashboard.jsx` → Rename to EditorDashboard, simplify
- `WriteupEditor.jsx` → Simplify for single editor use
- `PlayerPage.jsx` → Handle limited academy data gracefully

### Pages to Add
- `CurationDashboard.jsx` → Review/approve community takes
- `QuickTakeForm.jsx` → Public submission form (embeddable)
- `AcademyOverview.jsx` → View academy players by team (optional)

### Components to Add
- `CommunityTakeCard.jsx` → Display a single community take
- `TakeSubmissionForm.jsx` → Quick take submission
- `RedditTakeImporter.jsx` → Admin tool to import from Reddit

---

## Implementation Phases

### Phase 1: Foundation (Week 1-2)
**Goal:** Rebrand + simplify without breaking existing functionality

#### Tasks
| ID | Task | Status | Acceptance Criteria |
|----|------|--------|---------------------|
| 1.1 | Rename LoanedPlayer → TrackedPlayer with migration | `pending` | Migration runs, existing data preserved, tests pass |
| 1.2 | Add pathway_status, current_level, data_depth columns | `pending` | Columns added, defaults set for existing loans |
| 1.3 | Update API endpoints to use new model name | `pending` | All /loans endpoints work with /tracked-players alias |
| 1.4 | Remove Stripe integration (backend) | `pending` | All stripe_*.py routes removed, models deprecated |
| 1.5 | Remove Stripe integration (frontend) | `pending` | Stripe pages deleted, no Stripe imports remain |
| 1.6 | Remove writer recruitment flows | `pending` | Coverage request system removed |
| 1.7 | Simplify UserAccount roles | `pending` | Remove journalist tiers, keep admin + editor |
| 1.8 | Update branding: "Go On Loan" → "The Academy Watch" | `pending` | Logo, titles, copy updated across frontend |
| 1.9 | Run full test suite, fix breakages | `pending` | pnpm lint && pnpm test:e2e passes |

### Phase 2: Community Takes (Week 3-4)
**Goal:** Add community content aggregation

#### Tasks
| ID | Task | Status | Acceptance Criteria |
|----|------|--------|---------------------|
| 2.1 | Create CommunityTake model + migration | `complete` | Model created, migration runs |
| 2.2 | Create QuickTakeSubmission model + migration | `complete` | Model created, migration runs |
| 2.3 | Build submission API endpoints | `complete` | POST /community-takes/submit works |
| 2.4 | Build curation API endpoints | `complete` | Admin can approve/reject takes |
| 2.5 | Create QuickTakeForm component | `complete` | Form renders, validates, submits |
| 2.6 | Create CurationDashboard page | `complete` | Admin can view queue, approve/reject |
| 2.7 | Integrate takes into newsletter template | `complete` | Newsletter shows approved takes for players |
| 2.8 | Add submission link to newsletter footer | `complete` | Readers can submit takes from email |

### Phase 3: Reddit Integration (Week 5-6)
**Goal:** Aggregate takes from Reddit automatically

> **SKIPPED:** Reddit API access not available. Takes can still be manually added via the curation dashboard with source_type='reddit'.

#### Tasks
| ID | Task | Status | Acceptance Criteria |
|----|------|--------|---------------------|
| 3.1 | Create Reddit scraper service (PRAW) | `skipped` | Can fetch posts/comments from subreddit |
| 3.2 | Add subreddit → team mapping config | `skipped` | Admin can map r/reddevils → Man United |
| 3.3 | Build player mention detection | `skipped` | Scraper identifies which player a comment is about |
| 3.4 | Create admin scrape trigger endpoint | `skipped` | POST /admin/reddit/scrape works |
| 3.5 | Auto-create CommunityTakes from scrapes | `skipped` | Scraped content appears in curation queue |
| 3.6 | Add Reddit attribution display | `skipped` | Takes show "u/username on r/subreddit" |
| 3.7 | Schedule periodic scraping (optional) | `skipped` | Background job runs scraper weekly |

### Phase 4: Academy Tracking (Week 7-8)
**Goal:** Track academy players alongside loans

#### Tasks
| ID | Task | Status | Acceptance Criteria |
|----|------|--------|---------------------|
| 4.1 | Create AcademyLeague model + migration | `complete` | Model created, migration runs |
| 4.2 | Identify and seed relevant youth leagues | `pending` | Top 5-10 academy leagues configured |
| 4.3 | Build academy fixture sync | `complete` | Can fetch U21/U23 fixtures from API-Football |
| 4.4 | Track academy player appearances from lineups | `complete` | Players marked as "played" from lineup data |
| 4.5 | Track academy goals/assists from events | `complete` | Goals/assists recorded from event data |
| 4.6 | Add academy section to newsletter | `complete` | Newsletter includes "Academy Update" section |
| 4.7 | Handle "limited data" display gracefully | `complete` | UI shows "Played" vs detailed stats appropriately |
| 4.8 | Track pathway progression (academy → loan → first team) | `pending` | Player status updates when they progress |

### Phase 5: Polish & Launch (Week 9-10)
**Goal:** Production-ready release

#### Tasks
| ID | Task | Status | Acceptance Criteria |
|----|------|--------|---------------------|
| 5.1 | Full E2E test coverage for new features | `pending` | All new flows have Playwright tests |
| 5.2 | Update CLAUDE.md and AGENTS.md | `pending` | Documentation reflects new architecture |
| 5.3 | Performance review (query optimization) | `pending` | Key pages load < 2s |
| 5.4 | Security review (submission spam prevention) | `pending` | Rate limiting, IP hashing in place |
| 5.5 | Domain setup (theacademywatch.com) | `pending` | Domain purchased, DNS configured |
| 5.6 | Deploy to production | `pending` | New version live on Azure |
| 5.7 | Seed initial content (first newsletter) | `pending` | At least one newsletter with community takes |
| 5.8 | Reddit/Twitter announcement | `pending` | Launch post in relevant subreddits |

---

## Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| API-Football youth data gaps | High | Medium | Set expectations, focus on top leagues |
| Low community submission volume | High | High | Seed with Reddit content, your own takes |
| Reddit API rate limits | Medium | Medium | Cache aggressively, scrape infrequently |
| Spam submissions | Medium | Low | Rate limit, IP hash, optional email verify |
| Breaking existing functionality | Medium | High | Comprehensive test suite, phased rollout |

---

## Success Metrics

| Metric | Target (Month 1) | Target (Month 3) |
|--------|------------------|------------------|
| Weekly newsletter subscribers | 100 | 500 |
| Community takes submitted | 10/week | 50/week |
| Newsletter open rate | 30% | 40% |
| Reddit post engagement | 10 upvotes avg | 50 upvotes avg |

---

## Open Questions

- [ ] Which 2-3 clubs to focus on initially? (Suggest: Man United, Arsenal, Chelsea)
- [ ] Include transfer rumors/news or strictly performance tracking?
- [ ] Allow anonymous submissions or require email?
- [ ] Daily vs weekly newsletter cadence?

---

## Appendix: Current Codebase Reference

### Backend Key Files
- `loan-army-backend/src/models/league.py` - Core models (30+)
- `loan-army-backend/src/routes/api.py` - Main endpoints (591KB)
- `loan-army-backend/src/routes/journalist.py` - Writer endpoints (to remove)
- `loan-army-backend/src/routes/stripe_*.py` - Payment routes (to remove)
- `loan-army-backend/src/agents/` - AI newsletter generation

### Frontend Key Files
- `loan-army-frontend/src/lib/api.js` - API client (174 methods)
- `loan-army-frontend/src/pages/admin/` - Admin pages (14)
- `loan-army-frontend/src/pages/writer/` - Writer pages (to simplify)
- `loan-army-frontend/src/context/AuthContext.jsx` - Auth state

### Commands
```bash
# Backend dev
cd loan-army-backend && python src/main.py

# Frontend dev
cd loan-army-frontend && pnpm dev

# Tests
cd loan-army-frontend && pnpm lint && pnpm test:e2e

# Deploy
./deploy_aca.sh
```
