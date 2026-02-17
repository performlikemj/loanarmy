# Academy Watch Agent Fix Plan

## Problem
The chat agent on Academy Watch isn't returning any data. Three linked issues:

### 1. Backend: RunContext not passed to Runner.run() (ROOT CAUSE)
- `academy_watch_agent.py` stores DataFrames keyed by `session_id` in `_session_dataframes`
- Tool functions try to get `session_id` from `ctx` (RunContextWrapper)
- But `chat.py` calls `Runner.run(agent, messages)` WITHOUT passing a context object
- So `ctx.session_id` is always `None` → falls back to empty DataFrames
- **Fix:** Create a dataclass context, pass it via `Runner.run(agent, messages, context=ctx)`

### 2. Backend: No-scope sessions raise ValueError
- `load_context()` requires at least one of `team_id`, `league_id`, or `player_ids`
- If a session is created without these, it raises ValueError (caught, but results in empty data)
- **Fix:** Either require scope at creation OR load a default "all active loans" dataset

### 3. Frontend: ChatPanel not passing team/league context
- `<ChatPanel />` in AnalystPage is rendered without `teamId` or `leagueId` props
- The component accepts these props and passes them to `createChatSession`
- But the AnalystPage doesn't provide them
- **Fix:** Add a team/league selector UI before or within the chat, OR load all data by default

## Backend Changes (academy_watch_agent.py + chat.py)

### academy_watch_agent.py
```python
from dataclasses import dataclass

@dataclass
class ChatContext:
    session_id: int
```

Update tool signatures to use `RunContextWrapper[ChatContext]`:
```python
async def run_analytics(ctx: RunContextWrapper[ChatContext], args_str: str) -> str:
    args = RunAnalyticsArgs.model_validate_json(args_str)
    dataframes = _get_session_dataframes(ctx)
    ...
```

Update `_get_session_dataframes`:
```python
def _get_session_dataframes(ctx) -> dict:
    session_id = ctx.context.session_id if ctx and hasattr(ctx, 'context') else None
    ...
```

### chat.py
```python
from src.agents.academy_watch_agent import ChatContext

# In _run_agent_sync:
def _run_agent_sync(agent, messages, context):
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(asyncio.run, Runner.run(agent, messages, context=context))
        return future.result(timeout=60)

# In send_message:
chat_context = ChatContext(session_id=session.id)
result = _run_agent_sync(agent, messages, chat_context)
```

### dataframe_loader.py
- Make all filters optional → if none provided, load ALL active loans (with a row limit)
- This lets the general analyst page work without requiring team/league selection

## Frontend Changes (ChatPanel.jsx + AnalystPage)

### Option A: Context Selector (Recommended)
Add a team/league dropdown at the top of ChatPanel when no props are passed:
- Fetch teams list from existing `/api/teams` endpoint
- User selects a team (optional) before chatting
- Pass selection to `createChatSession`
- Also allow "All Teams" option (no filter)

### Option B: Global Chat (Simpler)
- Allow no-filter sessions (backend loads all active loans)
- Add context selector as optional enhancement later

**Recommendation:** Go with Option B first (unblock the feature), then add Option A as enhancement.

### Mobile Considerations
- ChatPanel is already responsive (flex layout, max-w-[85%] messages)
- Input area needs mobile keyboard handling (already has onKeyDown)
- Consider: sticky input on mobile, viewport height issues with keyboard
- Add `dvh` or `svh` units instead of fixed `h-[600px]` for mobile
- Touch-friendly suggestion chips (already decent size)

## Implementation Order
1. Backend: Add ChatContext dataclass + pass to Runner.run()
2. Backend: Make dataframe_loader work with no filters (load all active, capped)
3. Frontend: Update AnalystPage to allow no-context chat
4. Frontend: Add optional team selector dropdown
5. Frontend: Mobile polish (height, keyboard, touch targets)
