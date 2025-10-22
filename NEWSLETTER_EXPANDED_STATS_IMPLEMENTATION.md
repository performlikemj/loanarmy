# Newsletter Expanded Stats Implementation

**Date:** October 22, 2025  
**Status:** ✅ Complete - Ready for Testing

---

## Summary

Comprehensive player statistics are now included in both email and web newsletters, with position-specific stat displays that highlight the most relevant metrics for each player type.

---

## Changes Made

### 1. ✅ Newsletter Templates Updated

**Files Modified:**
- `loan-army-backend/src/templates/newsletter_email.html`
- `loan-army-backend/src/templates/newsletter_web.html`

**What Changed:**
- Added position-specific stat displays in the main stat line
- Support for both API-Football formats: full names (`Goalkeeper`, `Defender`, `Midfielder`, `Attacker`) and short codes (`G`, `D`, `M`, `F`)

**Position-Specific Stats Shown:**

| Position | Main Stats Displayed |
|----------|---------------------|
| **Goalkeeper** | `90' · 5 Saves · 2 Conceded` |
| **Defender** | `90' · 3T 2I` (+ goals/assists if any) |
| **Midfielder** | `90' · 1G 2A · 4 Key Passes` |
| **Forward/Attacker** | `90' · 2G 1A · 8 Shots` |

---

### 2. ✅ Backend Stats Aggregation

**File Modified:**
- `loan-army-backend/src/api_football_client.py`

**What Changed:**

#### `summarize_loanee_week()` method:
- Now queries `FixturePlayerStats` table from database
- Aggregates comprehensive stats including:
  - **Position info:** position, rating (averaged)
  - **Goalkeeper stats:** saves, goals_conceded
  - **Attacking stats:** shots_total, shots_on, dribbles_attempts, dribbles_success, offsides
  - **Passing stats:** passes_total, passes_key
  - **Defensive stats:** tackles_total, tackles_interceptions
  - **Physical stats:** duels_total, duels_won, fouls_drawn, fouls_committed
- Falls back to API data if database doesn't have stats yet
- Added `db_session` parameter to access database

#### `summarize_parent_loans_week()` method:
- Now passes `db_session` parameter to `summarize_loanee_week()`
- Supplemental entries include expanded stats structure with zeros

---

### 3. ✅ AI Agent Instructions Updated

**File Modified:**
- `loan-army-backend/src/agents/weekly_newsletter_agent.py`

**What Changed:**
- Updated `SYSTEM_PROMPT` to instruct AI to copy ALL fields from `report.loanees[*].totals` into the newsletter `stats` object
- Added comprehensive stats fields to the expected output schema
- AI now includes position, rating, saves, tackles, passes, shots, and all other available stats in generated newsletters

---

## Database Migration Required

**Migration File:** `migrations/versions/h1i2j3k4l5m6_expand_player_stats_comprehensive.py`

This migration adds 30+ new columns to the `fixture_player_stats` table.

### To Apply:

```bash
cd loan-army-backend

# Activate your virtual environment if needed
# source venv/bin/activate

# Apply the migration
flask db upgrade
```

### What the Migration Adds:

- **Basic info:** position, number, rating, captain, substitute
- **Attacking:** shots_total, shots_on, offsides, dribbles_attempts, dribbles_success, dribbles_past
- **Passing:** passes_total, passes_key, passes_accuracy
- **Defending:** tackles_total, tackles_blocks, tackles_interceptions
- **Physical:** duels_total, duels_won, fouls_drawn, fouls_committed
- **Penalties:** penalty_won, penalty_committed, penalty_scored, penalty_missed, penalty_saved
- **Goalkeeper:** goals_conceded, saves (already existed but now properly used)

---

## How It Works

### Data Flow:

1. **Fixture Fetch** → API-Football `/fixtures/players` endpoint fetches comprehensive stats
2. **Database Storage** → `_upsert_player_fixture_stats()` stores all stats in `fixture_player_stats` table
3. **Weekly Aggregation** → `summarize_loanee_week()` queries database and aggregates stats across fixtures
4. **Newsletter Generation** → AI agent receives full `totals` object and includes all stats in newsletter JSON
5. **Template Rendering** → Templates display position-specific stats based on player's position

### Example Newsletter Item:

```json
{
  "player_name": "H. Mejbri",
  "loan_team": "Birmingham City",
  "stats": {
    "minutes": 90,
    "goals": 1,
    "assists": 2,
    "yellows": 0,
    "reds": 0,
    "position": "Midfielder",
    "rating": 8.2,
    "saves": 0,
    "goals_conceded": 0,
    "shots_total": 4,
    "shots_on": 2,
    "passes_total": 65,
    "passes_key": 5,
    "tackles_total": 3,
    "tackles_interceptions": 2,
    "duels_total": 12,
    "duels_won": 8,
    "dribbles_attempts": 6,
    "dribbles_success": 4,
    "fouls_drawn": 2,
    "fouls_committed": 1,
    "offsides": 0
  },
  "week_summary": "...",
  "match_notes": ["..."]
}
```

### Template Display:

**Midfielder:**
```
90' · 1G 2A · 5 Key Passes · ⭐ 8.2 [M]
```

**Plus detailed stat grids below** (already existed, now populated with real data):
- ⚽ Attacking: Shots, Dribbles, Offsides
- 🎯 Passing: Total passes, Key passes, Accuracy
- 🛡️ Defending: Tackles, Interceptions, Blocks
- ⚔️ Duels: Won/Total
- ⚠️ Discipline: Fouls, Cards

---

## Testing Checklist

After running the migration:

- [ ] Generate a test newsletter for a team with active loanees
- [ ] Verify position-specific stats appear in the main stat line
- [ ] Check goalkeeper newsletters show saves/conceded instead of G/A
- [ ] Verify defender newsletters show tackles/interceptions
- [ ] Confirm midfielder newsletters show key passes
- [ ] Check forward newsletters show shots
- [ ] Verify the expanded stat grids display real data
- [ ] Test both email HTML and web HTML versions
- [ ] Confirm stats match what's in the database

---

## Next Steps

1. **Run Database Migration:**
   ```bash
   cd loan-army-backend
   flask db upgrade
   ```

2. **Generate a Test Newsletter:**
   - Use the admin interface or API to generate a newsletter for a team
   - Check both email and web versions

3. **Verify Stats Display:**
   - Goalkeepers should show saves/conceded
   - Defenders should show tackles/interceptions
   - Midfielders should show key passes
   - Forwards should show shots
   - All should show ratings if available

---

## Files Modified

- ✅ `loan-army-backend/src/templates/newsletter_email.html`
- ✅ `loan-army-backend/src/templates/newsletter_web.html`
- ✅ `loan-army-backend/src/api_football_client.py`
- ✅ `loan-army-backend/src/agents/weekly_newsletter_agent.py`

---

## Compatibility

- ✅ Backward compatible - newsletters will still generate even without the migration
- ✅ Graceful degradation - if stats aren't available, shows zeros
- ✅ Handles both API-Football position formats
- ✅ Works with supplemental loans (shows zeros for stats)

---

## Performance Impact

**Minimal** - The changes query the database which is more efficient than repeatedly calling the API:
- Database queries are indexed on `fixture_id` and `player_api_id`
- Stats are aggregated in Python (fast)
- No additional API calls required
- Results are cached during newsletter generation

---

🎉 **All changes complete! Run the migration and test the newsletters.**

