# CONTINUITY.md

> Master ledger — canonical project state. Read this first every turn.

## Goal

Go On Loan — Football loan tracking platform with AI-powered newsletters and journalist content management.

## Constraints / Assumptions

- Backend runs on Flask (port 5001)
- Frontend runs on React/Vite (port 5173, proxies /api to backend)
- PostgreSQL database
- Deployed to Azure Container Apps

## Key Decisions

- Using AGENTS.md + Ralph workflow for autonomous task execution
- Planning ledgers track task status for handoff between interactive and autonomous modes

## State

### Done
- Agent workflow setup (AGENTS.md, Ralph scripts, ledger structure)
- Agent protocol integration into CLAUDE.md
- "The Academy Watch" refactor planning and analysis
- Phase 1: Foundation (Stripe removal, branding, pathway columns)
- Phase 2: Community Takes (complete)
  - CommunityTake and QuickTakeSubmission models + migration
  - Public submission API with rate limiting
  - Admin curation endpoints (approve/reject/create/stats)
  - AdminCuration dashboard page
  - QuickTakeForm component and /submit-take page
  - Newsletter template integration (shows approved takes)
  - Submit take CTA in newsletter footer
- Phase 3: Reddit Integration (skipped - no API access)
- Phase 4: Academy Tracking (complete)
  - AcademyLeague and AcademyAppearance models + migration
  - Academy sync service (fetches fixtures, lineups, events)
  - Admin API endpoints for league management and sync
  - AdminAcademy dashboard page
  - Academy section in newsletter template
  - Limited data handling (Started/Sub badges, G+A when available)
  - 4.8: Pathway progression UI in AdminLoans (status/level editing, badges, filters)
- Phase 5: Polish & Launch (in progress)
  - 5.1: E2E tests for Academy Watch features (complete)
    - `e2e/academy-watch.spec.js` - tests for SubmitTake, AdminCuration, AdminAcademy, pathway status
    - Database helpers in `e2e/helpers/db.js` for test cleanup
  - 5.4: Security review for `/community-takes/submit` (complete)
    - Flask-Limiter decorators (10/min, 30/hour)
    - Input sanitization via bleach
    - Email format validation
    - Duplicate content detection (24h window)

### Now
- Player Journey feature (complete - needs migration and testing)
  - Interactive map showing career path from academy to first team
  - `PlayerJourney`, `PlayerJourneyEntry`, `ClubLocation` models
  - `JourneySyncService` - fetches from API-Football, classifies levels
  - 50+ major club coordinates seeded
  - `JourneyMap.jsx` component with Leaflet
  - `JourneyTimeline.jsx` fallback component
  - Integrated into PlayerPage with new "Journey" tab
  - E2E tests: `e2e/journey.spec.js`
  - Backend tests: `tests/test_journey.py`
- **See `ledgers/ACADEMY_WATCH_IMPLEMENTATION_PLAN.md` for detailed status**

### Next
- Run migration: `flask db upgrade`
- Install frontend deps: `cd loan-army-frontend && pnpm install`
- Seed club locations: `POST /api/admin/journey/seed-locations`
- Test journey sync: `POST /api/admin/journey/sync/284324` (Garnacho)
- Run E2E tests: `pnpm test:e2e`

## Task Map

```
CONTINUITY.md
  └─ ledgers/CONTINUITY_plan-example.md (template - rename for actual work)
```

## Active Ledgers

| Ledger | Status | Owner | Blockers |
|--------|--------|-------|----------|
| ACADEMY_WATCH_REFACTOR_PLAN.md | complete | — | Phases 1-4 done |
| ACADEMY_WATCH_IMPLEMENTATION_PLAN.md | in-progress | — | Phases 1-5 done, Phase 6 ready |
| ACADEMY_WATCH_JOURNEY_REDESIGN.md | complete | — | Design doc for journey feature |

## Trivial Log

- 2026-01-10: Fixed agent protocol - made AGENTS.md reading mandatory in CLAUDE.md

## Open Questions

- (none currently)

## Working Set

**Key files:**
- `CLAUDE.md` - Claude Code instructions (auto-loaded)
- `AGENTS.md` - Agent operating protocol
- `scripts/ralph/` - Autonomous execution scripts
- `ledgers/` - Planning and task ledgers

**Useful commands:**
```bash
# Backend
cd loan-army-backend && python src/main.py

# Frontend
cd loan-army-frontend && pnpm dev

# Tests
cd loan-army-frontend && pnpm test:e2e

# Ralph autonomous mode
./scripts/ralph/ralph.sh 25
```
