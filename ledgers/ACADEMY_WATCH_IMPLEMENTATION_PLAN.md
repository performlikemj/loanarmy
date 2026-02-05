# Academy Watch - Implementation Plan

> Complete rebuild of player journey tracking with interactive geographic visualization

---

## Vision

Track academy players' complete career journeys on an interactive world map. Users click club pins to see detailed stats for each stop — from U18 academy to first team and beyond.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        FRONTEND                                  │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐ │
│  │ JourneyMap  │  │ ClubDetail  │  │ JourneyTimeline         │ │
│  │ (Mapbox)    │──│ Drawer      │  │ (fallback/mobile)       │ │
│  └─────────────┘  └─────────────┘  └─────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                         BACKEND                                  │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐ │
│  │ Journey API │  │ Sync Service│  │ Club Geocoder           │ │
│  │ /journey/*  │  │ (Celery)    │  │ (coordinates lookup)    │ │
│  └─────────────┘  └─────────────┘  └─────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                        DATABASE                                  │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐ │
│  │ PlayerJourney│ │ JourneyEntry│  │ ClubLocation            │ │
│  └─────────────┘  └─────────────┘  └─────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

---

## Phase 1: Database Models & Migration
**Goal:** Create schema for journey tracking and club locations

### Tasks

| ID | Task | Status | Est |
|----|------|--------|-----|
| 1.1 | Create `PlayerJourney` model | `complete` | 30m |
| 1.2 | Create `PlayerJourneyEntry` model | `complete` | 30m |
| 1.3 | Create `ClubLocation` model (coordinates) | `complete` | 20m |
| 1.4 | Write migration script | `complete` | 20m |
| 1.5 | Seed club locations for major clubs | `complete` | 1h |

**Files created:**
- `src/models/journey.py` - All three models
- `migrations/versions/x2y3z4a5b6c7_add_player_journey_tables.py` - Migration
- `src/services/journey_sync.py` - Includes seed_club_locations()

### Models

```python
# PlayerJourney - Master journey record
class PlayerJourney(db.Model):
    __tablename__ = 'player_journeys'
    
    id = db.Column(db.Integer, primary_key=True)
    player_api_id = db.Column(db.Integer, nullable=False, unique=True, index=True)
    player_name = db.Column(db.String(200))
    player_photo = db.Column(db.String(500))
    
    # Origin (first club)
    origin_club_api_id = db.Column(db.Integer)
    origin_club_name = db.Column(db.String(200))
    
    # Current status
    current_club_api_id = db.Column(db.Integer)
    current_club_name = db.Column(db.String(200))
    current_level = db.Column(db.String(30))  # 'U18', 'U21', 'First Team', 'On Loan'
    
    # Milestones
    first_team_debut_date = db.Column(db.String(20))  # YYYY-MM-DD or season
    first_team_debut_club = db.Column(db.String(200))
    first_team_debut_competition = db.Column(db.String(200))
    
    # Aggregates
    total_clubs = db.Column(db.Integer, default=0)
    total_first_team_apps = db.Column(db.Integer, default=0)
    total_youth_apps = db.Column(db.Integer, default=0)
    total_goals = db.Column(db.Integer, default=0)
    
    # Sync tracking
    seasons_synced = db.Column(db.JSON)  # [2019, 2020, 2021, ...]
    last_synced_at = db.Column(db.DateTime)
    sync_error = db.Column(db.Text)
    
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, onupdate=lambda: datetime.now(timezone.utc))
    
    entries = db.relationship('PlayerJourneyEntry', backref='journey', lazy='dynamic',
                              order_by='PlayerJourneyEntry.season.desc(), PlayerJourneyEntry.sort_priority.desc()')


# PlayerJourneyEntry - Each club/season combination
class PlayerJourneyEntry(db.Model):
    __tablename__ = 'player_journey_entries'
    
    id = db.Column(db.Integer, primary_key=True)
    journey_id = db.Column(db.Integer, db.ForeignKey('player_journeys.id'), nullable=False, index=True)
    
    # Season
    season = db.Column(db.Integer, nullable=False)  # e.g., 2021
    
    # Club info
    club_api_id = db.Column(db.Integer, nullable=False)
    club_name = db.Column(db.String(200))
    club_logo = db.Column(db.String(500))
    
    # League/Competition info
    league_api_id = db.Column(db.Integer)
    league_name = db.Column(db.String(200))
    league_country = db.Column(db.String(100))
    
    # Classification
    level = db.Column(db.String(30))  # 'U18', 'U19', 'U21', 'U23', 'Reserve', 'First Team'
    entry_type = db.Column(db.String(30))  # 'academy', 'first_team', 'loan', 'permanent', 'international'
    is_youth = db.Column(db.Boolean, default=False)
    is_international = db.Column(db.Boolean, default=False)
    
    # Stats
    appearances = db.Column(db.Integer, default=0)
    goals = db.Column(db.Integer, default=0)
    assists = db.Column(db.Integer, default=0)
    minutes = db.Column(db.Integer, default=0)
    
    # Sorting (higher = more prominent)
    sort_priority = db.Column(db.Integer, default=0)
    # First Team Senior = 100, First Team Cup = 90, U23 = 50, U21 = 40, U19 = 30, U18 = 20, International = 80
    
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    
    __table_args__ = (
        db.Index('ix_journey_entry_lookup', 'journey_id', 'season', 'club_api_id'),
    )


# ClubLocation - Coordinates for map display
class ClubLocation(db.Model):
    __tablename__ = 'club_locations'
    
    id = db.Column(db.Integer, primary_key=True)
    club_api_id = db.Column(db.Integer, unique=True, nullable=False, index=True)
    club_name = db.Column(db.String(200))
    
    # Location
    city = db.Column(db.String(100))
    country = db.Column(db.String(100))
    country_code = db.Column(db.String(5))
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)
    
    # Source tracking
    geocode_source = db.Column(db.String(50))  # 'manual', 'mapbox', 'google', 'osm'
    geocode_confidence = db.Column(db.Float)  # 0-1
    
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, onupdate=lambda: datetime.now(timezone.utc))
```

---

## Phase 2: Journey Sync Service
**Goal:** Build service to fetch and process player career data from API-Football

### Tasks

| ID | Task | Status | Est |
|----|------|--------|-----|
| 2.1 | Create `JourneySyncService` class | `complete` | 1h |
| 2.2 | Implement level classification logic | `complete` | 30m |
| 2.3 | Implement first-team debut detection | `complete` | 30m |
| 2.4 | Add entry deduplication (same club/season) | `complete` | 30m |
| 2.5 | Create admin sync endpoint | `complete` | 30m |
| 2.6 | Add background job for bulk sync | `pending` | 30m |

**Files created:**
- `src/services/journey_sync.py` - Full sync service with classification

### Core Logic

```python
class JourneySyncService:
    """Syncs player journey data from API-Football"""
    
    LEVEL_PATTERNS = {
        'U18': ['u18', 'under 18', 'under-18'],
        'U19': ['u19', 'under 19', 'youth league'],
        'U21': ['u21', 'under 21'],
        'U23': ['u23', 'under 23', 'premier league 2', 'pl2'],
        'Reserve': ['reserve', 'b team', 'ii'],
    }
    
    PRIORITY_MAP = {
        'First Team': 100,
        'International': 80,
        'U23': 50,
        'U21': 40,
        'U19': 30,
        'U18': 20,
        'Reserve': 45,
    }
    
    def sync_player(self, player_api_id: int, force_full: bool = False) -> PlayerJourney:
        """Sync complete journey for a player"""
        # Implementation here
        pass
    
    def classify_level(self, team_name: str, league_name: str) -> str:
        """Determine level from team/league names"""
        pass
    
    def detect_first_team_debut(self, entries: List[PlayerJourneyEntry]) -> dict:
        """Find earliest first-team appearance"""
        pass
```

---

## Phase 3: Club Location Data
**Goal:** Build and populate club coordinates database

### Tasks

| ID | Task | Status | Est |
|----|------|--------|-----|
| 3.1 | Create geocoding utility | `complete` | 30m |
| 3.2 | Seed Top 5 league clubs (100+ clubs) | `complete` | 1h |
| 3.3 | Seed major youth academies | `pending` | 30m |
| 3.4 | Add fallback geocoding for unknown clubs | `pending` | 30m |

**Note:** 50+ major club locations seeded in `seed_club_locations()`

### Initial Club Seed (Priority Clubs)

```python
MAJOR_CLUBS = [
    # Premier League
    {'api_id': 33, 'name': 'Manchester United', 'city': 'Manchester', 'country': 'England', 'lat': 53.4631, 'lng': -2.2913},
    {'api_id': 40, 'name': 'Liverpool', 'city': 'Liverpool', 'country': 'England', 'lat': 53.4308, 'lng': -2.9608},
    {'api_id': 42, 'name': 'Arsenal', 'city': 'London', 'country': 'England', 'lat': 51.5549, 'lng': -0.1084},
    {'api_id': 49, 'name': 'Chelsea', 'city': 'London', 'country': 'England', 'lat': 51.4817, 'lng': -0.1910},
    {'api_id': 50, 'name': 'Manchester City', 'city': 'Manchester', 'country': 'England', 'lat': 53.4831, 'lng': -2.2004},
    {'api_id': 47, 'name': 'Tottenham', 'city': 'London', 'country': 'England', 'lat': 51.6042, 'lng': -0.0662},
    # ... more clubs
    
    # La Liga
    {'api_id': 541, 'name': 'Real Madrid', 'city': 'Madrid', 'country': 'Spain', 'lat': 40.4531, 'lng': -3.6883},
    {'api_id': 529, 'name': 'Barcelona', 'city': 'Barcelona', 'country': 'Spain', 'lat': 41.3809, 'lng': 2.1228},
    {'api_id': 530, 'name': 'Atletico Madrid', 'city': 'Madrid', 'country': 'Spain', 'lat': 40.4362, 'lng': -3.5995},
    # ... etc
]
```

---

## Phase 4: Backend API Endpoints
**Goal:** Create REST endpoints for journey data

### Tasks

| ID | Task | Status | Est |
|----|------|--------|-----|
| 4.1 | `GET /api/players/:id/journey` - Full journey | `complete` | 30m |
| 4.2 | `GET /api/players/:id/journey/map` - Map-optimized | `complete` | 30m |
| 4.3 | `POST /api/admin/journey/sync/:id` - Trigger sync | `complete` | 20m |
| 4.4 | `POST /api/admin/journey/bulk-sync` - Bulk sync | `complete` | 20m |
| 4.5 | `POST /api/admin/journey/seed-locations` - Seed locations | `complete` | 20m |
| 4.6 | `GET /api/club-locations` - Get all locations | `complete` | 20m |
| 4.7 | `POST /api/admin/club-locations` - Add location | `complete` | 20m |

**Endpoints added to:** `src/routes/api.py`

### API Response Shapes

```json
// GET /api/players/284324/journey
{
  "player": {
    "id": 284324,
    "name": "A. Garnacho",
    "photo": "https://..."
  },
  "origin": {
    "club_id": 530,
    "club_name": "Atletico Madrid",
    "year": 2019
  },
  "current": {
    "club_id": 33,
    "club_name": "Manchester United",
    "level": "First Team"
  },
  "milestones": {
    "first_team_debut": {
      "date": "2022",
      "club": "Manchester United",
      "competition": "Premier League"
    }
  },
  "totals": {
    "clubs": 2,
    "first_team_apps": 74,
    "youth_apps": 58,
    "goals": 27
  },
  "entries": [
    {
      "season": 2024,
      "club_id": 33,
      "club_name": "Manchester United",
      "club_logo": "https://...",
      "level": "First Team",
      "competitions": [
        {"name": "Premier League", "apps": 36, "goals": 6, "assists": 2},
        {"name": "Europa League", "apps": 15, "goals": 1, "assists": 4}
      ],
      "location": {"lat": 53.4631, "lng": -2.2913}
    },
    // ... more entries
  ]
}

// GET /api/players/284324/journey/map
{
  "player_name": "A. Garnacho",
  "stops": [
    {
      "club_id": 530,
      "club_name": "Atletico Madrid",
      "club_logo": "https://...",
      "lat": 40.4362,
      "lng": -3.5995,
      "years": "2019",
      "levels": ["U19"],
      "total_apps": 12,
      "total_goals": 3
    },
    {
      "club_id": 33,
      "club_name": "Manchester United",
      "club_logo": "https://...",
      "lat": 53.4631,
      "lng": -2.2913,
      "years": "2020-present",
      "levels": ["U18", "U21", "First Team"],
      "total_apps": 132,
      "total_goals": 27,
      "breakdown": {
        "U18": {"apps": 13, "goals": 9},
        "U21": {"apps": 45, "goals": 11},
        "First Team": {"apps": 74, "goals": 15}
      }
    }
  ],
  "path": [[40.4362, -3.5995], [53.4631, -2.2913]]
}
```

---

## Phase 5: Frontend - Journey Map Component
**Goal:** Build interactive map visualization

### Tasks

| ID | Task | Status | Est |
|----|------|--------|-----|
| 5.1 | Install Leaflet (free alternative to Mapbox) | `complete` | 15m |
| 5.2 | Create `JourneyMap` component | `complete` | 2h |
| 5.3 | Create `ClubStopMarker` component | `complete` | 30m |
| 5.4 | Create `ClubDetailDrawer` component | `complete` | 1h |
| 5.5 | Add journey path animation | `complete` | 1h |
| 5.6 | Create `JourneyTimeline` component (mobile/fallback) | `complete` | 1h |
| 5.7 | Add API client methods | `complete` | 20m |

**Files created:**
- `src/components/JourneyMap.jsx` - Interactive map with Leaflet
- `src/components/JourneyTimeline.jsx` - Timeline fallback view
- Updated `src/lib/api.js` with journey methods
- Updated `package.json` with leaflet, react-leaflet

### Component Structure

```jsx
// JourneyMap.jsx
<div className="journey-map-container">
  <MapboxMap
    center={mapCenter}
    zoom={3}
  >
    {/* Journey path line */}
    <JourneyPath stops={stops} />
    
    {/* Club markers */}
    {stops.map(stop => (
      <ClubMarker
        key={stop.club_id}
        position={[stop.lat, stop.lng]}
        club={stop}
        isOrigin={stop === stops[0]}
        isCurrent={stop === stops[stops.length - 1]}
        onClick={() => setSelectedStop(stop)}
      />
    ))}
  </MapboxMap>
  
  {/* Detail drawer */}
  <ClubDetailDrawer
    open={!!selectedStop}
    stop={selectedStop}
    onClose={() => setSelectedStop(null)}
  />
</div>
```

### ClubDetailDrawer Content

```jsx
// When user clicks a club pin
<Drawer>
  <div className="club-header">
    <img src={stop.club_logo} />
    <h2>{stop.club_name}</h2>
    <span>{stop.years}</span>
  </div>
  
  <div className="levels-summary">
    {stop.levels.map(level => (
      <Badge>{level}</Badge>
    ))}
  </div>
  
  <div className="stats-breakdown">
    {Object.entries(stop.breakdown).map(([level, stats]) => (
      <div className="level-row">
        <span className="level-name">{level}</span>
        <span>{stats.apps} apps</span>
        <span>{stats.goals} goals</span>
      </div>
    ))}
  </div>
  
  <div className="competitions">
    <h3>Competitions</h3>
    {stop.competitions.map(comp => (
      <div>{comp.name}: {comp.apps} apps, {comp.goals}G {comp.assists}A</div>
    ))}
  </div>
</Drawer>
```

---

## Phase 6: Integration & Polish
**Goal:** Wire everything together and polish UX

### Tasks

| ID | Task | Status | Est |
|----|------|--------|-----|
| 6.1 | Integrate JourneyMap into PlayerPage | `complete` | 30m |
| 6.2 | Add loading states and error handling | `complete` | 30m |
| 6.3 | Add "Sync Journey" button for admin | `pending` | 20m |
| 6.4 | Performance optimization (lazy load map) | `complete` | 30m |
| 6.5 | E2E tests for journey feature | `complete` | 1h |
| 6.6 | Backend unit tests | `complete` | 30m |

**Files modified:**
- `src/pages/PlayerPage.jsx` - Added Journey tab with lazy loading
- `e2e/journey.spec.js` - E2E tests
- `tests/test_journey.py` - Backend unit tests

---

## Technical Decisions

### Map Library: Mapbox GL JS
- Free tier: 50k map loads/month
- Better styling than Leaflet
- Good React integration via react-map-gl
- Smooth animations for journey paths

### Geocoding Strategy
1. Manual seed for top ~200 clubs (most accurate)
2. Mapbox geocoding API for unknown clubs (fallback)
3. Cache all results in ClubLocation table

### Sync Strategy
- On-demand: Admin can trigger sync for specific player
- Background: Nightly job syncs all tracked players
- Rate limit: Max 100 API calls per sync batch

---

## Timeline Estimate

| Phase | Duration | Dependencies |
|-------|----------|--------------|
| Phase 1: Database | 2-3 hours | None |
| Phase 2: Sync Service | 3-4 hours | Phase 1 |
| Phase 3: Club Locations | 2 hours | Phase 1 |
| Phase 4: API Endpoints | 2 hours | Phase 2, 3 |
| Phase 5: Frontend Map | 5-6 hours | Phase 4 |
| Phase 6: Integration | 2-3 hours | Phase 5 |

**Total: ~18-20 hours of implementation**

---

## Open Items

- [ ] Mapbox API key needed (or use free Leaflet alternative)
- [ ] Decide: Show international caps on map? (separate pin or grouped with club?)
- [ ] Decide: How far back to sync? (5 years? All available?)

---

## Files to Create/Modify

### New Files
```
loan-army-backend/
  src/models/journey.py              # New models
  src/services/journey_sync.py       # Sync service
  src/services/geocoding.py          # Club location service
  migrations/versions/xxx_journey.py # Migration

loan-army-frontend/
  src/components/JourneyMap.jsx      # Map component
  src/components/ClubMarker.jsx      # Map marker
  src/components/ClubDetailDrawer.jsx # Click detail
  src/components/JourneyTimeline.jsx # Fallback/mobile
```

### Modified Files
```
loan-army-backend/
  src/routes/api.py                  # Add journey endpoints
  src/models/__init__.py             # Export new models

loan-army-frontend/
  src/pages/PlayerPage.jsx           # Integrate map
  src/lib/api.js                     # Add journey API calls
  package.json                       # Add mapbox deps
```
