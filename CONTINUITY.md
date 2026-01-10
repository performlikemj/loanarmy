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

### Now
- Agent protocol integration into CLAUDE.md

### Next
- Create actual planning ledger when ready for autonomous work

## Task Map

```
CONTINUITY.md
  └─ ledgers/CONTINUITY_plan-example.md (template - rename for actual work)
```

## Active Ledgers

| Ledger | Status | Owner | Blockers |
|--------|--------|-------|----------|
| CONTINUITY_plan-example.md | template | — | Rename and populate for actual tasks |

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
