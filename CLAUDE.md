# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Go On Loan** is a football (soccer) loan tracking platform that monitors players on loan, generates AI-powered newsletters, and enables journalists to write content about loaned players. It integrates with API-Football for player/fixture data, Stripe for payments, Mailgun for email delivery, and Reddit for social posting.

## Development Commands

### Backend (Flask)
```bash
cd loan-army-backend

# Run development server (port 5001)
python src/main.py

# Run with virtual environment
../.loan/bin/python src/main.py

# Database migrations
flask db upgrade                    # Apply migrations
flask db migrate -m "description"   # Create new migration
flask db downgrade                  # Rollback one migration
```

### Frontend (React/Vite)
```bash
cd loan-army-frontend

pnpm install          # Install dependencies
pnpm dev              # Dev server (port 5173, proxies /api to :5001)
pnpm build            # Production build
pnpm lint             # ESLint
```

### Testing
```bash
cd loan-army-frontend

# Run all Playwright E2E tests
pnpm test:e2e

# Run a single test file
pnpm exec playwright test tests/admin-teams.test.mjs

# Run tests with UI
pnpm exec playwright test --ui
```

### Deployment
```bash
# Full deployment to Azure Container Apps
./deploy_aca.sh
```

## Architecture

### Tech Stack
- **Frontend**: React 19 + Vite 6 + Tailwind CSS 4 + Radix UI
- **Backend**: Flask 3.1 + SQLAlchemy 2.0 + Alembic
- **Database**: PostgreSQL
- **Deployment**: Azure Container Apps (backend), Azure Static Web App (frontend)

### Directory Structure
```
loan-army-backend/src/
├── main.py                 # Flask app initialization
├── routes/
│   ├── api.py              # Main API endpoints (50+)
│   ├── journalist.py       # Writer/journalist endpoints
│   └── stripe_*.py         # Stripe payment routes
├── models/
│   ├── league.py           # Core domain models (35+)
│   └── weekly.py           # Fixture/stats models
├── services/               # Business logic (email, reddit, stripe)
├── agents/                 # AI newsletter generation
└── utils/                  # Team resolution, markdown, sanitization

loan-army-frontend/src/
├── pages/admin/            # Admin dashboard (14 pages)
├── pages/writer/           # Writer interface
├── components/ui/          # Radix-based UI components
└── lib/api.js              # API service wrapper
```

### Key Data Flow
1. **Loan Detection**: API-Football → `LoanedPlayer` records
2. **Stats Sync**: Fixtures → `FixturePlayerStats` → aggregated player stats
3. **Newsletters**: Admin creates → Writers add commentaries → Email delivery via Mailgun
4. **Payments**: Stripe Connect for writer monetization (10% platform fee)

### API Proxy
Frontend dev server proxies `/api/*` requests to `http://localhost:5001` (see `vite.config.js`).

## Important Patterns

### Database Models
Core models in `loan-army-backend/src/models/league.py`:
- `Team`, `LoanedPlayer`, `Newsletter` - core domain
- `UserAccount`, `UserSubscription` - users and email subscriptions
- `JournalistTeamAssignment` - writer assignments to teams
- `StripeConnectedAccount`, `StripeSubscription` - payments

Weekly models in `models/weekly.py`:
- `Fixture`, `FixturePlayerStats` - match and performance data

### Team Name Resolution
`resolve_team_name_and_logo()` in `api.py` handles team ID → name resolution with caching to `TeamProfile`.

### Player Stats
- **Full coverage** (top leagues): Aggregated from `FixturePlayerStats`
- **Limited coverage** (lower leagues): Denormalized columns on `LoanedPlayer`

## Environment Variables

Key variables (see `loan-army-backend/env.template` for full list):
- `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, `DB_NAME` - PostgreSQL
- `API_FOOTBALL_KEY`, `API_FOOTBALL_MODE` - Football data API
- `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET` - Payments
- `MAILGUN_API_KEY`, `MAILGUN_DOMAIN` - Email delivery
- `ADMIN_API_KEY` - Admin endpoint authentication

## Session Continuity

This project uses `CONTINUITY.md` as a session ledger (see `AGENTS.md` for conventions). Update it when goals, decisions, or state changes to survive context compaction.
