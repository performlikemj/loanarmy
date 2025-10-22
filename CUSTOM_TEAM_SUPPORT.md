# ⚽ Custom Team Support for Manual Players

**Status:** ✅ Complete  
**Date:** October 7, 2025

---

## 🎯 Problem Solved

**Issue:** Players are often loaned to teams outside the top European leagues (Championship, League One, League Two, non-European leagues) that aren't in your database.

**Solution:** Added ability to enter custom team names for teams not in the database, while still supporting dropdown selection for teams that ARE in the database.

---

## ✨ What's New

### Before:
```
❌ Could only select teams from database dropdown
❌ Couldn't add players loaned to Championship, League One, etc.
❌ Couldn't add players loaned to non-European teams
❌ Limited to ~100 top European league teams
```

### After:
```
✅ Select from dropdown OR enter custom team name
✅ Checkbox to toggle "Custom team" mode
✅ Works for both Primary Team and Loan Team
✅ Can track loans to ANY team worldwide
✅ Examples: Portsmouth, Sunderland, Sheffield Wednesday, Hull City
```

---

## 🎨 UI Design

### Form Layout:

```
┌─────────────────────────────────────────────────────────┐
│ Primary Team (Parent Club) *          [✓] Custom team   │
│ [Dropdown of teams ▼]                                   │
└─────────────────────────────────────────────────────────┘

When checkbox is checked:
┌─────────────────────────────────────────────────────────┐
│ Primary Team (Parent Club) *          [✓] Custom team   │
│ [Portsmouth________________________________]             │
└─────────────────────────────────────────────────────────┘
```

### User Flow:

#### Scenario 1: Player loaned to team in database
```
1. Primary Team: Select "Chelsea" from dropdown
2. Loan Team: Select "Brighton" from dropdown ✓
```

#### Scenario 2: Player loaned to Championship team
```
1. Primary Team: Select "Manchester City" from dropdown  
2. Loan Team: Check [✓] Custom team
3. Type: "Sheffield Wednesday" ✓
```

#### Scenario 3: Both teams custom (rare case)
```
1. Primary Team: Check [✓] Custom team → Type "Portsmouth"
2. Loan Team: Check [✓] Custom team → Type "Plymouth Argyle" ✓
```

---

## 🔧 Implementation

### Database Changes

#### 1. Migration: Make Team IDs Nullable
**File:** `migrations/versions/m7n8o9p0q1r2_make_team_ids_nullable_for_custom_teams.py`

```python
def upgrade():
    """Make team_id foreign keys nullable to support custom teams."""
    
    with op.batch_alter_table('loaned_players') as batch_op:
        # Drop and recreate foreign key constraints
        batch_op.drop_constraint('loaned_players_primary_team_id_fkey')
        batch_op.drop_constraint('loaned_players_loan_team_id_fkey')
        
        # Make columns nullable
        batch_op.alter_column('primary_team_id', nullable=True)
        batch_op.alter_column('loan_team_id', nullable=True)
        
        # Recreate foreign key constraints (now nullable)
        batch_op.create_foreign_key(..., 'teams', ['primary_team_id'], ['id'])
        batch_op.create_foreign_key(..., 'teams', ['loan_team_id'], ['id'])
```

**Key Change:** `primary_team_id` and `loan_team_id` can now be NULL in `loaned_players` table.

---

#### 2. Model Update
**File:** `src/models/league.py`

```python
class LoanedPlayer(db.Model):
    # ...
    primary_team_id = db.Column(db.Integer, db.ForeignKey('teams.id'), 
                                 nullable=True)  # ✅ Now nullable
    primary_team_name = db.Column(db.String(100), nullable=False)  # Always required
    
    loan_team_id = db.Column(db.Integer, db.ForeignKey('teams.id'), 
                             nullable=True)  # ✅ Now nullable
    loan_team_name = db.Column(db.String(100), nullable=False)  # Always required
```

**Pattern:**
- If team is in database: `team_id` = database ID, `team_name` = database name
- If custom team: `team_id` = NULL, `team_name` = user-entered name

---

### Backend Changes

#### API Endpoint Update
**File:** `src/routes/api.py`

**New Request Parameters:**
```python
# Option 1: Team from database
{
  "primary_team_id": 123,
  "loan_team_id": 456
}

# Option 2: Custom team name
{
  "custom_primary_team_name": "Portsmouth",
  "custom_loan_team_name": "Sheffield Wednesday"
}

# Option 3: Mix (primary from DB, loan custom)
{
  "primary_team_id": 123,
  "custom_loan_team_name": "Hull City"
}
```

**Backend Logic:**
```python
@api_bp.route('/admin/players', methods=['POST'])
def admin_create_player():
    # Handle primary team
    if data.get('primary_team_id'):
        # Team from database
        primary_team = Team.query.get(primary_team_id)
        primary_team_name = primary_team.name
        primary_team_api_id = primary_team.team_id
    elif data.get('custom_primary_team_name'):
        # Custom team
        primary_team_id = None  # NULL in database
        primary_team_name = custom_primary_team_name
        primary_team_api_id = None
    else:
        return error('Primary team is required')
    
    # Same logic for loan team...
    
    # Create LoanedPlayer with potentially NULL team_ids
    loaned_player = LoanedPlayer(
        primary_team_id=primary_team_id,  # May be None
        primary_team_name=primary_team_name,  # Always set
        loan_team_id=loan_team_id,  # May be None
        loan_team_name=loan_team_name,  # Always set
        # ...
    )
```

**Key Features:**
- ✅ Validates that either `team_id` OR `custom_team_name` is provided
- ✅ Looks up team details if using database team
- ✅ Sets `team_id` to NULL for custom teams
- ✅ Always sets `team_name` (either from DB or user input)
- ✅ Builds `team_ids` string only with valid API IDs

---

### Frontend Changes

#### 1. Form State Update
**File:** `src/App.jsx`

```javascript
const [addPlayerForm, setAddPlayerForm] = useState({
  name: '',
  primary_team_id: '',
  loan_team_id: '',
  window_key: '',
  
  // NEW: Custom team flags and names
  use_custom_primary_team: false,
  custom_primary_team_name: '',
  use_custom_loan_team: false,
  custom_loan_team_name: '',
  
  // ... other fields ...
})
```

---

#### 2. Form UI - Conditional Rendering

```jsx
<div>
  <div className="flex items-center justify-between mb-1">
    <label>Primary Team (Parent Club) *</label>
    <label className="cursor-pointer">
      <input
        type="checkbox"
        checked={addPlayerForm.use_custom_primary_team}
        onChange={(e) => setAddPlayerForm({
          ...addPlayerForm,
          use_custom_primary_team: e.target.checked,
          primary_team_id: '',  // Clear dropdown value
          custom_primary_team_name: ''  // Clear text input
        })}
      />
      Custom team
    </label>
  </div>
  
  {/* Show text input if custom, dropdown otherwise */}
  {addPlayerForm.use_custom_primary_team ? (
    <input
      type="text"
      placeholder="e.g. Portsmouth, Sunderland"
      value={addPlayerForm.custom_primary_team_name}
      onChange={(e) => setAddPlayerForm({
        ...addPlayerForm,
        custom_primary_team_name: e.target.value
      })}
    />
  ) : (
    <TeamSelect
      teams={runTeams}
      value={addPlayerForm.primary_team_id}
      onChange={(id) => setAddPlayerForm({
        ...addPlayerForm,
        primary_team_id: id
      })}
    />
  )}
</div>

{/* Same pattern for Loan Team */}
```

**UX Flow:**
1. By default: Show team dropdown
2. Check "Custom team": Switch to text input
3. Uncheck: Switch back to dropdown
4. Switching clears the other field's value

---

#### 3. Validation Logic

```javascript
const createManualPlayer = async () => {
  // Validate primary team
  if (!addPlayerForm.use_custom_primary_team && !addPlayerForm.primary_team_id) {
    return error('Primary team is required (or check "Custom team")')
  }
  if (addPlayerForm.use_custom_primary_team && !addPlayerForm.custom_primary_team_name.trim()) {
    return error('Custom primary team name is required')
  }
  
  // Validate loan team
  if (!addPlayerForm.use_custom_loan_team && !addPlayerForm.loan_team_id) {
    return error('Loan team is required (or check "Custom team")')
  }
  if (addPlayerForm.use_custom_loan_team && !addPlayerForm.custom_loan_team_name.trim()) {
    return error('Custom loan team name is required')
  }
  
  // Build payload conditionally
  const payload = {
    name: addPlayerForm.name.trim(),
    window_key: addPlayerForm.window_key
  }
  
  if (addPlayerForm.use_custom_primary_team) {
    payload.custom_primary_team_name = addPlayerForm.custom_primary_team_name.trim()
  } else {
    payload.primary_team_id = parseInt(addPlayerForm.primary_team_id)
  }
  
  if (addPlayerForm.use_custom_loan_team) {
    payload.custom_loan_team_name = addPlayerForm.custom_loan_team_name.trim()
  } else {
    payload.loan_team_id = parseInt(addPlayerForm.loan_team_id)
  }
  
  await APIService.adminPlayerCreate(payload)
}
```

---

## 📊 Database Records

### Example 1: Both Teams in Database
```sql
-- LoanedPlayer record
player_name: "Noni Madueke"
primary_team_id: 789  -- Chelsea FK
primary_team_name: "Chelsea"
loan_team_id: 456  -- Brighton FK
loan_team_name: "Brighton & Hove Albion"
team_ids: "49,51"  -- API IDs
```

### Example 2: Loan Team Custom
```sql
-- LoanedPlayer record
player_name: "Cole Palmer"
primary_team_id: 789  -- Manchester City FK
primary_team_name: "Manchester City"
loan_team_id: NULL  -- ✅ No FK (custom team)
loan_team_name: "Sheffield Wednesday"  -- User-entered
team_ids: "50"  -- Only primary team API ID
```

### Example 3: Both Custom (rare)
```sql
-- LoanedPlayer record
player_name: "Some Player"
primary_team_id: NULL  -- ✅ No FK
primary_team_name: "Portsmouth"  -- User-entered
loan_team_id: NULL  -- ✅ No FK
loan_team_name: "Plymouth Argyle"  -- User-entered
team_ids: NULL  -- No API IDs available
```

---

## ✅ Benefits

### Data Tracking:
- ✅ **Track ANY loan worldwide:** Not limited to top leagues
- ✅ **Championship support:** Sheffield Wednesday, Hull City, Sunderland, etc.
- ✅ **Lower leagues:** League One, League Two, National League
- ✅ **International loans:** Can track loans to any country

### Database Integrity:
- ✅ **No fake teams:** Don't create Team records for non-tracked teams
- ✅ **Clean data:** team_id is NULL for custom teams (not a fake ID)
- ✅ **team_name always set:** Can always display loan information

### User Experience:
- ✅ **Flexible:** Use dropdown for known teams, text for others
- ✅ **Fast:** Quick checkbox toggle
- ✅ **Clear:** Shows placeholder examples
- ✅ **Validating:** Won't let you submit empty custom names

---

## 🎯 Use Cases

### Championship Loans:
```
Player: Liam Delap
Primary Team: Manchester City (dropdown)
Loan Team: ✓ Custom → "Hull City"
```

### League One Loans:
```
Player: James McAtee
Primary Team: Manchester City (dropdown)
Loan Team: ✓ Custom → "Sheffield Wednesday"
```

### Non-European Loans:
```
Player: Some Player
Primary Team: Chelsea (dropdown)
Loan Team: ✓ Custom → "Al-Nassr (Saudi Arabia)"
```

### Both Custom (rare):
```
Player: Academy Player
Primary Team: ✓ Custom → "Norwich City"
Loan Team: ✓ Custom → "Ipswich Town"
```

---

## 📝 Migration Instructions

### To Apply Changes:

1. **Run Migration:**
```bash
cd loan-army-backend
flask db upgrade
```

This will:
- Make `primary_team_id` nullable
- Make `loan_team_id` nullable
- Recreate foreign key constraints

2. **Verify:**
```bash
# Check database schema
psql -U user -d database -c "\d loaned_players"

# Should show:
# primary_team_id | integer | nullable
# loan_team_id | integer | nullable
```

---

## 🔍 Finding Custom Teams

### In Players Hub:
```
Player: Cole Palmer
Teams: Manchester City → Sheffield Wednesday
Loan Count: 1

🟢 M badge indicates manual player
🔵 Custom team names displayed normally
```

### Filtering Behavior:
```
Filter by "Manchester City":
✓ Shows players with primary_team_id = Manchester City ID
✓ Shows players with loan_team_id = Manchester City ID
✗ Does NOT show players with custom_team_name = "Manchester City"
   (because team_id is NULL)
```

**Note:** Custom teams won't appear when filtering by team dropdown, since they don't have a team_id. They'll only show in search or when viewing all players.

---

## ⚠️ Limitations

### Custom Teams:
1. **No filtering by custom teams** - Can't filter Players Hub by "Hull City" if it's a custom name
2. **No stats auto-fetch** - Custom teams don't have API IDs, so can't auto-fetch stats
3. **Manual entry required** - Must type team name exactly each time

### Workaround:
If a team becomes popular enough, you can manually add it to the `teams` table with a fake team_id (negative number), then it becomes available in dropdowns.

---

## 🎉 Summary

### What Changed:
✅ **Database:** Made team_ids nullable in LoanedPlayer  
✅ **Backend:** Handle both database teams and custom names  
✅ **Frontend:** Checkbox to toggle custom team input  
✅ **Validation:** Ensure either team_id or custom_name provided  

### Result:
**Players can now be loaned to ANY team, not just top European leagues!**

Common examples:
- Championship: Hull City, Sheffield Wednesday, Sunderland, Portsmouth
- League One: Plymouth Argyle, Ipswich Town, Bolton Wanderers
- International: Al-Nassr, Inter Miami, Any team worldwide

---

**Custom Team Support Complete! Track loans to ANY team! ⚽✨**

