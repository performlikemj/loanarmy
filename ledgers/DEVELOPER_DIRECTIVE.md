# Developer Directive: The Academy Watch Refactor

**Last Updated:** 2026-01-30
**Status:** Phase 4 Complete, Phase 5 Pending

---

## Project Context

"Go On Loan" is being rebranded to "The Academy Watch" - expanding from loan tracking to include academy player tracking and community-sourced content.

---

## Completed Work

### Phase 1: Foundation ✅
- Removed Stripe integration (backend routes, frontend pages, context)
- Removed writer recruitment system (coverage requests, external writers)
- Added pathway tracking columns to `LoanedPlayer`: `pathway_status`, `current_level`, `data_depth`
- Rebranded to "The Academy Watch" across UI and email templates
- Migration: `aw01_add_pathway_tracking_columns.py`

### Phase 2: Community Takes ✅
- **Models:** `CommunityTake`, `QuickTakeSubmission` in `models/league.py`
- **Migration:** `aw02_add_community_takes_tables.py`
- **Backend:** `routes/community_takes.py` - submission API, admin curation endpoints
- **Frontend:**
  - `pages/admin/AdminCuration.jsx` - curation dashboard
  - `components/QuickTakeForm.jsx` - submission form
  - `pages/SubmitTake.jsx` - public submission page at `/submit-take`
- **Newsletter:** Community takes section + "Share Your Take" CTA in footer

### Phase 3: Reddit Integration ⏭️ SKIPPED
- No Reddit API access available
- Takes can still be manually added via curation dashboard with `source_type='reddit'`

### Phase 4: Academy Tracking ✅
- **Models:** `AcademyLeague`, `AcademyAppearance` in `models/league.py`
- **Migration:** `aw03_add_academy_tracking_tables.py`
- **Backend:**
  - `services/academy_sync_service.py` - fetches fixtures, extracts lineups/events
  - `routes/academy.py` - league CRUD, sync triggers, appearance queries
- **Frontend:**
  - `pages/admin/AdminAcademy.jsx` - league management dashboard
  - API methods in `lib/api.js`
  - Sidebar link added
- **Newsletter:** Academy Update section showing player appearances

---

## Remaining Work

### Phase 4 Remaining Task

**4.8: Pathway Progression Tracking** - COMPLETE
- Implemented admin UI to update pathway status via AdminLoans page
- Added `pathway_status`, `current_level`, `data_depth` to `LoanedPlayer.to_dict()`
- Added pathway field handling in `admin_update_loan` endpoint
- Added pathway status/level dropdowns in loan edit form
- Added pathway status badge display in loan list
- Added pathway filter in filter bar
- Values: `'academy'` | `'on_loan'` | `'first_team'` | `'released'`
- Levels: `'U18'` | `'U21'` | `'U23'` | `'Reserve'` | `'Senior'`

### Phase 5: Polish & Launch

| Task | Description | Priority |
|------|-------------|----------|
| 5.1 | E2E test coverage for new features - COMPLETE | High |
| 5.2 | Update CLAUDE.md with new architecture | Medium |
| 5.3 | Performance review - query optimization for newsletter rendering | Medium |
| 5.4 | Security review - COMPLETE | High |
| 5.5 | Domain setup (theacademywatch.com) | Low |
| 5.6 | Deploy to production | High |
| 5.7 | Seed initial academy leagues (Premier League 2, etc.) | Medium |
| 5.8 | Social announcement | Low |

---

## Key Files to Know

### Backend
```
src/models/league.py          # All models including new ones
src/routes/community_takes.py # Community takes API
src/routes/academy.py         # Academy tracking API
src/services/academy_sync_service.py # Fixture sync logic
src/templates/newsletter_email.html  # Email template with new sections
```

### Frontend
```
src/pages/admin/AdminCuration.jsx  # Curation dashboard
src/pages/admin/AdminAcademy.jsx   # Academy league management
src/components/QuickTakeForm.jsx   # Submission form component
src/pages/SubmitTake.jsx           # Public submission page
src/lib/api.js                     # API methods (search for "Community Takes" and "Academy")
src/components/admin/AdminSidebar.jsx # Sidebar with new links
```

### Migrations (apply in order)
```
aw01_add_pathway_tracking_columns.py
aw02_add_community_takes_tables.py
aw03_add_academy_tracking_tables.py
```

---

## Testing the New Features

### 1. Apply Migrations
```bash
cd loan-army-backend
flask db upgrade
```

### 2. Test Community Takes
- Go to `/submit-take` and submit a take
- Go to `/admin/curation` to approve/reject
- Preview a newsletter to see approved takes

### 3. Test Academy Tracking
- Go to `/admin/academy` and add a league (need API-Football league ID)
- Click sync to fetch fixtures
- Set a player's `pathway_status` to `'academy'` to see them in newsletter

### 4. Run E2E Tests
```bash
cd loan-army-frontend
pnpm exec playwright test e2e/academy-watch.spec.js
```

Test file: `e2e/academy-watch.spec.js`
- Community Takes: submit, view pending, approve, create directly
- Academy Tracking: access page, create league, delete league
- Pathway Status: view/edit in AdminLoans, filter by status

Database helpers added to `e2e/helpers/db.js`:
- `cleanupTestSubmissions`, `cleanupTestCommunityTakes`, `cleanupTestAcademyLeagues`
- `getFirstActiveLoan`, `getLoanedPlayerById`

---

## Security Measures

### `/community-takes/submit` Endpoint

**Rate Limiting (Defense in Depth):**
1. Flask-Limiter: 10 requests/minute, 30 requests/hour per IP
2. Database-level: 5 submissions per IP per hour (using hashed IP)

**Input Validation & Sanitization:**
- Content length limit: 280 characters
- All text inputs sanitized via bleach (XSS prevention)
- Email format validation with regex
- Email length limit: 254 characters

**Spam Prevention:**
- IP hashing for privacy-preserving tracking
- User-Agent logging
- Duplicate content detection (24-hour window)

**Response Codes:**
- 400: Invalid input
- 429: Rate limit exceeded

---

## Known Issues

1. **Pre-existing lint errors** in `App.jsx` (undefined variables like `authToken`) - not from this refactor
2. **E2E test environment** has `process undefined` errors - pre-existing config issue
3. Some "Go On Loan" references remain in non-user-facing files (docs, config)

---

## API-Football League IDs (for seeding)

Common youth leagues to configure:
- Premier League 2 (Division 1): Look up on api-football.com
- EFL Trophy (includes U21 teams)
- UEFA Youth League

Use the admin UI at `/admin/academy` to add leagues.

---

## Architecture Notes

### Community Takes Flow
```
User submits → QuickTakeSubmission (pending)
            → Admin approves → CommunityTake (approved)
            → Shows in newsletter
```

### Academy Sync Flow
```
Admin configures AcademyLeague
            → Sync triggered (manual or scheduled)
            → Fetches fixtures from API-Football
            → Extracts lineups → AcademyAppearance records
            → Extracts events → Updates goals/assists/cards
            → Newsletter renders appearances for pathway_status='academy' players
```

### Newsletter Rendering
Context built in `_newsletter_render_context()` in `api.py`:
- Fetches `community_takes` for newsletter/team
- Fetches `academy_appearances` for date range + academy players
- Passes to Jinja template
