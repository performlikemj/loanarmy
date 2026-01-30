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
- Ready for Phase 5: Polish & Launch, or testing current features
- **See `ledgers/DEVELOPER_DIRECTIVE.md` for detailed handoff notes**

### Next
- Phase 5: Polish & Launch (E2E tests, performance, deployment)

## Task Map

```
CONTINUITY.md
  └─ ledgers/CONTINUITY_plan-example.md (template - rename for actual work)
```

## Active Ledgers

| Ledger | Status | Owner | Blockers |
|--------|--------|-------|----------|
| ACADEMY_WATCH_REFACTOR_PLAN.md | ready | — | Awaiting review before implementation |
| ACADEMY_WATCH_AGENT_DIRECTIVE.md | ready | — | Agent implementation guide |

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
