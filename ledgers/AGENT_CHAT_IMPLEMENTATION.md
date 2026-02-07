# Academy Watch Chat Agent — Implementation Ledger

## Plan

### Phase 1: Backend Models + Migration
- [x] `src/models/chat.py` — ChatSession, ChatMessage models
- [x] Alembic migration for chat tables
- [x] Update `src/main.py` to import chat models

### Phase 2: Agent Factory
- [x] `src/agents/academy_watch_agent.py` — Agent with tools:
  - `refresh_player_stats` — fetch fresh stats from API-Football (Pydantic validated)
  - `get_player_journey` — get career path data
  - `run_analytics` — execute Python code in sandbox against DataFrames
- [x] `src/services/analytics_sandbox.py` — sandboxed code execution
  - subprocess with no network
  - allowlist: pandas, numpy, matplotlib, plotly, json
  - 256MB memory, 10s timeout
  - returns base64 images + JSON tables
- [x] `src/services/dataframe_loader.py` — load DB data into DataFrames
  - df_players, df_loans, df_matches, df_journeys

### Phase 3: Chat API Routes
- [x] `src/routes/chat.py` — Blueprint with:
  - POST /api/chat/sessions — create session (auth required)
  - POST /api/chat/sessions/:id/messages — send message (auth + rate limit)
  - GET /api/chat/sessions — list user sessions
  - GET /api/chat/sessions/:id/history — get messages
  - DELETE /api/chat/sessions/:id — soft delete
- [x] Register blueprint in main.py

### Phase 4: Frontend
- [x] `src/components/chat/ChatPanel.jsx` — chat UI component
- [x] `src/components/chat/ChartRenderer.jsx` — render agent chart output
- [x] `src/components/chat/DataTableRenderer.jsx` — render tabular output
- [x] Add ChatPanel to App.jsx routes (auth-gated at /analyst)
- [x] API service methods for chat endpoints

### Phase 5: Tests
- [ ] `tests/test_chat_api.py` — route tests
- [ ] `tests/test_analytics_sandbox.py` — sandbox security tests
- [ ] `tests/test_dataframe_loader.py` — data loading tests

## Constraints
- All on feature branch `feature/academy-chat-agent`
- Never push to main without MJ's approval
- TDD approach where practical
- SQLAlchemy ORM only — NO raw SQL
- All tool inputs Pydantic-validated with types, ranges, enums
- Sandbox: no network, no filesystem, no DB access, 256MB, 10s timeout

## Review Cycle
Opus implements → Codex reviews → Opus fixes → repeat
