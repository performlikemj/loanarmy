# Academy Watch - Journey Redesign

> Redesigning the player journey feature to accurately track academy → first team progression

---

## Data Discovery Summary

### What API-Football Provides

✅ **Available per season:**
- Youth team appearances (U18, U19, U21, U23)
- Youth league competitions (FA Youth Cup, UEFA Youth League, PL2, U18 Premier League)
- Goals, assists from youth matches
- First team debut appearances
- Loan spells
- International youth caps

✅ **Players/seasons endpoint:** Lists all seasons a player has data for
✅ **Players endpoint (by season):** Returns stats for ALL teams/leagues that season

### Example: Garnacho's Journey (from API)

| Season | Level | Team | League | Apps | Goals |
|--------|-------|------|--------|------|-------|
| 2021 | U18 | Man United U18 | FA Youth Cup | 6 | 7 |
| 2021 | U18 | Man United U18 | U18 Premier League | 7 | 2 |
| 2021 | U23 | Man United U23 | PL2 Division One | 12 | 4 |
| 2021 | U19 | Man United U19 | UEFA Youth League | 7 | 2 |
| 2021 | **First Team** | Manchester United | Premier League | 2 | 0 |
| 2022 | U21 | Man United U21 | PL2 Division One | 38 | 7 |
| 2022 | **First Team** | Manchester United | Premier League | 19 | 3 |
| 2022 | **First Team** | Manchester United | Europa League | 6 | 1 |
| 2024 | **First Team** | Manchester United | Premier League | 36 | 6 |

---

## New Data Model

### PlayerJourney (new model)
```python
class PlayerJourney(db.Model):
    """Tracks a player's complete career journey from academy to present"""
    __tablename__ = 'player_journeys'
    
    id = db.Column(db.Integer, primary_key=True)
    player_api_id = db.Column(db.Integer, nullable=False, index=True)
    player_name = db.Column(db.String(200))
    
    # Computed journey metadata
    origin_club_id = db.Column(db.Integer)  # First club in journey
    origin_club_name = db.Column(db.String(200))
    current_club_id = db.Column(db.Integer)
    current_club_name = db.Column(db.String(200))
    current_level = db.Column(db.String(20))  # 'U18', 'U21', 'First Team', 'On Loan'
    
    # Key milestones (denormalized for quick display)
    first_team_debut_date = db.Column(db.Date)
    first_team_debut_club = db.Column(db.String(200))
    first_team_debut_league = db.Column(db.String(200))
    total_first_team_apps = db.Column(db.Integer, default=0)
    total_youth_apps = db.Column(db.Integer, default=0)
    total_loan_apps = db.Column(db.Integer, default=0)
    
    # Tracking
    last_synced_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, onupdate=datetime.now(timezone.utc))
    
    # Relationship to detailed journey entries
    entries = db.relationship('PlayerJourneyEntry', backref='journey', lazy='dynamic')
```

### PlayerJourneyEntry (new model)
```python
class PlayerJourneyEntry(db.Model):
    """Individual season/team entry in a player's journey"""
    __tablename__ = 'player_journey_entries'
    
    id = db.Column(db.Integer, primary_key=True)
    journey_id = db.Column(db.Integer, db.ForeignKey('player_journeys.id'), nullable=False)
    
    # Season context
    season = db.Column(db.Integer, nullable=False)  # e.g., 2021
    
    # Team/League info
    team_api_id = db.Column(db.Integer)
    team_name = db.Column(db.String(200))
    team_logo = db.Column(db.String(500))
    league_api_id = db.Column(db.Integer)
    league_name = db.Column(db.String(200))
    league_country = db.Column(db.String(100))
    
    # Classification
    level = db.Column(db.String(30))  # 'U18', 'U19', 'U21', 'U23', 'Reserve', 'First Team', 'Loan', 'International'
    entry_type = db.Column(db.String(30))  # 'academy', 'first_team', 'loan', 'transfer', 'international'
    
    # Stats
    appearances = db.Column(db.Integer, default=0)
    goals = db.Column(db.Integer, default=0)
    assists = db.Column(db.Integer, default=0)
    minutes = db.Column(db.Integer, default=0)
    
    # For ordering within a season
    sort_priority = db.Column(db.Integer, default=0)  # First team = 100, U21 = 50, U18 = 30, etc.
    
    created_at = db.Column(db.DateTime, default=datetime.now(timezone.utc))
```

---

## Classification Logic

### Level Detection (from team name + league name)
```python
def classify_level(team_name: str, league_name: str) -> str:
    """Determine the level from team/league names"""
    team_lower = team_name.lower()
    league_lower = league_name.lower()
    
    # International
    if any(x in league_lower for x in ['world cup', 'euro', 'copa', 'friendlies', 'qualification']):
        if 'u20' in league_lower or 'u21' in league_lower or 'u19' in league_lower:
            return 'International Youth'
        return 'International'
    
    # Academy levels
    if 'u18' in team_lower or 'u18' in league_lower:
        return 'U18'
    if 'u19' in team_lower or 'u19' in league_lower or 'youth league' in league_lower:
        return 'U19'
    if 'u21' in team_lower or 'u21' in league_lower:
        return 'U21'
    if 'u23' in team_lower or 'premier league 2' in league_lower:
        return 'U23'
    if 'reserve' in team_lower or 'b team' in team_lower:
        return 'Reserve'
    
    # First team (default for top-flight leagues)
    top_leagues = ['premier league', 'la liga', 'serie a', 'bundesliga', 'ligue 1', 
                   'fa cup', 'league cup', 'europa', 'champions']
    if any(x in league_lower for x in top_leagues):
        return 'First Team'
    
    return 'First Team'  # Default
```

### Entry Type Detection
```python
def classify_entry_type(level: str, team_name: str, origin_club: str) -> str:
    """Determine if academy, first team, loan, etc."""
    if 'International' in level:
        return 'international'
    if level in ['U18', 'U19', 'U21', 'U23', 'Reserve']:
        return 'academy'
    # If team is different from origin club, it's likely a loan or transfer
    if team_name.lower() != origin_club.lower():
        return 'loan_or_transfer'  # Need transfer history to distinguish
    return 'first_team'
```

---

## Journey Sync Service

### Algorithm
```python
def sync_player_journey(player_api_id: int):
    """Sync complete journey for a player from API-Football"""
    
    # 1. Get all seasons for player
    seasons = api.get_player_seasons(player_api_id)
    
    # 2. For each season, get all team/league stats
    all_entries = []
    for season in sorted(seasons):
        player_data = api.get_player(player_api_id, season)
        for stat in player_data['statistics']:
            entry = PlayerJourneyEntry(
                season=season,
                team_api_id=stat['team']['id'],
                team_name=stat['team']['name'],
                team_logo=stat['team']['logo'],
                league_api_id=stat['league']['id'],
                league_name=stat['league']['name'],
                league_country=stat['league']['country'],
                level=classify_level(stat['team']['name'], stat['league']['name']),
                appearances=stat['games']['appearences'] or 0,
                goals=stat['goals']['total'] or 0,
                assists=stat['goals']['assists'] or 0,
                minutes=stat['games']['minutes'] or 0,
            )
            all_entries.append(entry)
    
    # 3. Determine origin club (earliest academy team)
    origin = find_origin_club(all_entries)
    
    # 4. Find first team debut
    debut = find_first_team_debut(all_entries)
    
    # 5. Create/update PlayerJourney record
    journey = PlayerJourney(
        player_api_id=player_api_id,
        player_name=player_data['player']['name'],
        origin_club_name=origin['club_name'],
        first_team_debut_date=debut['date'] if debut else None,
        # ... etc
    )
    
    # 6. Save entries
    for entry in all_entries:
        entry.journey_id = journey.id
        db.session.add(entry)
    
    db.session.commit()
```

---

## Frontend: Interactive Journey Visualization

### Journey Timeline Component
```
2019 ─────────────────────────────────────────────────────────────────
       ├─ [Atlético Madrid B] U19 - 12 apps, 3 goals
       
2020 ─────────────────────────────────────────────────────────────────
       ├─ [Manchester United U18] FA Youth Cup - 6 apps, 7 goals ⚽⚽⚽⚽⚽⚽⚽
       ├─ [Manchester United U18] U18 Premier League - 7 apps, 2 goals
       
2021 ─────────────────────────────────────────────────────────────────
       ├─ [Manchester United U23] PL2 Division One - 12 apps, 4 goals
       ├─ [Manchester United U19] UEFA Youth League - 7 apps, 2 goals
       ├─ [Manchester United] 🎉 FIRST TEAM DEBUT - 2 apps ⭐
       
2022 ─────────────────────────────────────────────────────────────────
       ├─ [Manchester United U21] PL2 Division One - 38 apps, 7 goals
       ├─ [Manchester United] Premier League - 19 apps, 3 goals
       ├─ [Manchester United] Europa League - 6 apps, 1 goal
       ├─ [Argentina U20] Maurice Revello - 4 apps, 4 goals 🇦🇷
       
2024 ─────────────────────────────────────────────────────────────────
       ├─ [Manchester United] Premier League - 36 apps, 6 goals
       └─ [Argentina] World Cup Qualifiers - 4 apps, 1 goal 🇦🇷
```

### Interactive Map (Optional Phase 2)
- Show clubs on a world map
- Animate the journey path
- Click on each stop for stats

---

## API Endpoints

### Public
```
GET /api/players/:id/journey
  → Returns complete journey timeline

GET /api/academy/graduates
  → List academy players who reached first team (filterable by club)

GET /api/academy/rising
  → Current academy players with standout recent performances
```

### Admin
```
POST /api/admin/journey/sync/:player_id
  → Trigger sync for specific player

POST /api/admin/journey/bulk-sync
  → Sync journeys for all tracked players

GET /api/admin/journey/sync-status
  → Show last sync, errors, pending players
```

---

## Migration Plan

### Phase 1: New Models (no breaking changes)
1. Create `player_journeys` and `player_journey_entries` tables
2. Keep existing `LoanedPlayer` model working
3. Add journey sync as background job

### Phase 2: Populate Journeys
1. For each tracked player, run journey sync
2. Build journey timeline in frontend
3. Replace current loan_history with journey timeline

### Phase 3: Deprecate Old Models
1. Migrate remaining loan data to journey model
2. Remove `LoanedPlayer` dependencies
3. Archive old loan tracking code

---

## Open Questions

- [ ] How far back to sync? (Suggest: 5 years or from academy entry)
- [ ] Include friendlies in journey? (Suggest: yes, but lower priority)
- [ ] Track international youth separately? (Suggest: yes, it's compelling data)
- [ ] Rate limit on bulk sync? (100 players = ~300 API calls)

---

## Quota Estimate

Per player sync:
- 1 call for seasons list
- N calls for each season (avg ~5 seasons)
- Total: ~6 calls per player

For 100 players: ~600 API calls
Pro plan: 7,500/day → Comfortable
