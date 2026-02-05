"""
Journey Sync Service

Fetches and processes player career data from API-Football to build
complete journey records with academy, loan, and first team data.
"""

import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from sqlalchemy.exc import IntegrityError

from src.models.league import db
from src.models.journey import (
    PlayerJourney, PlayerJourneyEntry, ClubLocation,
    LEVEL_PRIORITY, YOUTH_LEVELS
)
from src.api_football_client import APIFootballClient

logger = logging.getLogger(__name__)


class JourneySyncService:
    """Service for syncing player journey data from API-Football"""
    
    # Patterns to detect youth/academy levels
    LEVEL_PATTERNS = {
        'U18': ['u18', 'under 18', 'under-18', 'youth cup'],
        'U19': ['u19', 'under 19', 'under-19', 'youth league'],
        'U21': ['u21', 'under 21', 'under-21'],
        'U23': ['u23', 'under 23', 'under-23', 'premier league 2', 'pl2', 'development'],
        'Reserve': ['reserve', 'b team', ' ii', ' b ', 'second team'],
    }
    
    # Top-flight leagues that indicate first team level
    TOP_LEAGUES = [
        'premier league', 'la liga', 'serie a', 'bundesliga', 'ligue 1',
        'eredivisie', 'primeira liga', 'scottish premiership',
        'fa cup', 'league cup', 'efl cup', 'carabao',
        'champions league', 'europa league', 'conference league',
        'copa del rey', 'coppa italia', 'dfb-pokal', 'coupe de france',
        'community shield', 'supercopa', 'super cup',
    ]
    
    # International competitions
    INTERNATIONAL_PATTERNS = [
        'world cup', 'euro', 'copa america', 'african cup', 'asian cup',
        'gold cup', 'nations league', 'friendlies', 'qualification',
        'u20 world', 'u17 world', 'olympic', 'toulon', 'maurice revello',
    ]
    
    def __init__(self, api_client: Optional[APIFootballClient] = None):
        """Initialize with optional API client"""
        self.api = api_client or APIFootballClient()
    
    def sync_player(self, player_api_id: int, force_full: bool = False) -> Optional[PlayerJourney]:
        """
        Sync complete journey for a player.
        
        Args:
            player_api_id: API-Football player ID
            force_full: If True, re-sync all seasons even if already synced
            
        Returns:
            PlayerJourney record or None if sync failed
        """
        logger.info(f"Starting journey sync for player {player_api_id}")
        
        try:
            # Get or create journey record
            journey = PlayerJourney.query.filter_by(player_api_id=player_api_id).first()
            if not journey:
                journey = PlayerJourney(player_api_id=player_api_id)
                db.session.add(journey)
            
            # Get all seasons for this player
            seasons = self._get_player_seasons(player_api_id)
            if not seasons:
                journey.sync_error = "No seasons found for player"
                db.session.commit()
                return journey
            
            logger.info(f"Found {len(seasons)} seasons for player {player_api_id}: {seasons}")
            
            # Determine which seasons to sync
            already_synced = set(journey.seasons_synced or [])
            if force_full:
                seasons_to_sync = seasons
            else:
                # Always sync current and previous season, plus any new ones
                current_year = datetime.now().year
                seasons_to_sync = [
                    s for s in seasons 
                    if s not in already_synced or s >= current_year - 1
                ]
            
            # Fetch and process each season
            all_entries = []
            player_info = None
            
            for season in sorted(seasons_to_sync):
                try:
                    player_data = self._get_player_season_data(player_api_id, season)
                    if not player_data:
                        continue
                    
                    # Extract player info from first successful response
                    if not player_info and 'player' in player_data:
                        player_info = player_data['player']
                    
                    # Process statistics into entries
                    for stat in player_data.get('statistics', []):
                        entry = self._create_entry_from_stat(journey.id, season, stat)
                        if entry:
                            all_entries.append(entry)
                    
                except Exception as e:
                    logger.warning(f"Failed to fetch season {season} for player {player_api_id}: {e}")
                    continue
            
            # Update player info
            if player_info:
                journey.player_name = player_info.get('name')
                journey.player_photo = player_info.get('photo')
                birth = player_info.get('birth', {})
                journey.birth_date = birth.get('date')
                journey.birth_country = birth.get('country')
                journey.nationality = player_info.get('nationality')
            
            # Remove old entries for synced seasons and add new ones
            if all_entries:
                synced_seasons = set(e.season for e in all_entries)
                PlayerJourneyEntry.query.filter(
                    PlayerJourneyEntry.journey_id == journey.id,
                    PlayerJourneyEntry.season.in_(synced_seasons)
                ).delete(synchronize_session=False)
                
                for entry in all_entries:
                    entry.journey_id = journey.id
                    db.session.add(entry)
            
            # Update journey aggregates
            self._update_journey_aggregates(journey)
            
            # Update sync tracking
            journey.seasons_synced = sorted(set((journey.seasons_synced or []) + seasons_to_sync))
            journey.last_synced_at = datetime.now(timezone.utc)
            journey.sync_error = None
            
            db.session.commit()
            logger.info(f"Successfully synced journey for player {player_api_id}: {len(all_entries)} entries")
            
            return journey
            
        except Exception as e:
            logger.error(f"Failed to sync journey for player {player_api_id}: {e}")
            db.session.rollback()
            
            # Try to save error state
            try:
                journey = PlayerJourney.query.filter_by(player_api_id=player_api_id).first()
                if journey:
                    journey.sync_error = str(e)
                    db.session.commit()
            except:
                pass
            
            return None
    
    def _get_player_seasons(self, player_api_id: int) -> List[int]:
        """Get all seasons a player has data for"""
        try:
            response = self.api._make_request('players/seasons', {'player': player_api_id})
            seasons = response.get('response', [])
            return [int(s) for s in seasons if isinstance(s, (int, str)) and str(s).isdigit()]
        except Exception as e:
            logger.error(f"Failed to get seasons for player {player_api_id}: {e}")
            return []
    
    def _get_player_season_data(self, player_api_id: int, season: int) -> Optional[Dict]:
        """Get player data for a specific season"""
        try:
            response = self.api._make_request('players', {'id': player_api_id, 'season': season})
            data = response.get('response', [])
            return data[0] if data else None
        except Exception as e:
            logger.error(f"Failed to get player {player_api_id} season {season}: {e}")
            return None
    
    def _create_entry_from_stat(self, journey_id: int, season: int, stat: Dict) -> Optional[PlayerJourneyEntry]:
        """Create a journey entry from API-Football statistics block"""
        team = stat.get('team', {})
        league = stat.get('league', {})
        games = stat.get('games', {})
        goals = stat.get('goals', {})
        
        team_id = team.get('id')
        league_id = league.get('id')
        
        if not team_id:
            return None
        
        # Skip entries with no appearances
        appearances = games.get('appearences') or games.get('appearances') or 0
        if appearances == 0:
            return None
        
        team_name = team.get('name', '')
        league_name = league.get('name', '')
        
        # Classify the entry
        level = self._classify_level(team_name, league_name)
        entry_type = self._classify_entry_type(level, league_name)
        is_youth = level in YOUTH_LEVELS
        is_international = self._is_international(league_name)
        
        entry = PlayerJourneyEntry(
            journey_id=journey_id,
            season=season,
            club_api_id=team_id,
            club_name=team_name,
            club_logo=team.get('logo'),
            league_api_id=league_id,
            league_name=league_name,
            league_country=league.get('country'),
            league_logo=league.get('logo'),
            level=level,
            entry_type=entry_type,
            is_youth=is_youth,
            is_international=is_international,
            appearances=appearances,
            goals=goals.get('total') or 0,
            assists=goals.get('assists') or 0,
            minutes=games.get('minutes') or 0,
            sort_priority=LEVEL_PRIORITY.get(level, 0),
        )
        
        return entry
    
    def _classify_level(self, team_name: str, league_name: str) -> str:
        """Determine the level (U18, U21, First Team, etc.) from team/league names"""
        team_lower = team_name.lower()
        league_lower = league_name.lower()
        combined = f"{team_lower} {league_lower}"
        
        # Check for youth levels
        for level, patterns in self.LEVEL_PATTERNS.items():
            for pattern in patterns:
                if pattern in combined:
                    return level
        
        # Check for international
        if self._is_international(league_name):
            # Check if it's youth international
            if any(x in league_lower for x in ['u17', 'u18', 'u19', 'u20', 'u21', 'u23', 'youth']):
                return 'International Youth'
            return 'International'
        
        # Check for top-flight leagues (first team)
        for top_league in self.TOP_LEAGUES:
            if top_league in league_lower:
                return 'First Team'
        
        # Default to first team for unrecognized leagues
        return 'First Team'
    
    def _classify_entry_type(self, level: str, league_name: str) -> str:
        """Classify entry type (academy, first_team, international, etc.)"""
        if 'International' in level:
            return 'international'
        if level in YOUTH_LEVELS:
            return 'academy'
        return 'first_team'
    
    def _is_international(self, league_name: str) -> bool:
        """Check if league is international"""
        league_lower = league_name.lower()
        return any(pattern in league_lower for pattern in self.INTERNATIONAL_PATTERNS)
    
    def _update_journey_aggregates(self, journey: PlayerJourney):
        """Update aggregate stats on the journey record"""
        entries = PlayerJourneyEntry.query.filter_by(journey_id=journey.id).all()
        
        if not entries:
            return
        
        # Find origin (earliest entry)
        earliest = min(entries, key=lambda e: (e.season, -e.sort_priority))
        journey.origin_club_api_id = earliest.club_api_id
        journey.origin_club_name = earliest.club_name
        journey.origin_year = earliest.season
        
        # Find current (latest entry with highest priority)
        latest_season = max(e.season for e in entries)
        latest_entries = [e for e in entries if e.season == latest_season]
        current = max(latest_entries, key=lambda e: e.sort_priority)
        journey.current_club_api_id = current.club_api_id
        journey.current_club_name = current.club_name
        journey.current_level = current.level
        
        # Find first team debut
        first_team_entries = [e for e in entries if e.level == 'First Team' and not e.is_international]
        if first_team_entries:
            debut = min(first_team_entries, key=lambda e: e.season)
            journey.first_team_debut_season = debut.season
            journey.first_team_debut_club_id = debut.club_api_id
            journey.first_team_debut_club = debut.club_name
            journey.first_team_debut_competition = debut.league_name
            debut.is_first_team_debut = True
        
        # Calculate totals
        unique_clubs = set(e.club_api_id for e in entries if not e.is_international)
        journey.total_clubs = len(unique_clubs)
        
        journey.total_first_team_apps = sum(
            e.appearances for e in entries 
            if e.level == 'First Team' and not e.is_international
        )
        journey.total_youth_apps = sum(
            e.appearances for e in entries if e.is_youth
        )
        journey.total_goals = sum(e.goals for e in entries)
        journey.total_assists = sum(e.assists for e in entries)


def seed_club_locations():
    """Seed initial club locations for major clubs"""
    
    MAJOR_CLUBS = [
        # Premier League
        {'api_id': 33, 'name': 'Manchester United', 'city': 'Manchester', 'country': 'England', 'code': 'GB', 'lat': 53.4631, 'lng': -2.2913},
        {'api_id': 40, 'name': 'Liverpool', 'city': 'Liverpool', 'country': 'England', 'code': 'GB', 'lat': 53.4308, 'lng': -2.9608},
        {'api_id': 42, 'name': 'Arsenal', 'city': 'London', 'country': 'England', 'code': 'GB', 'lat': 51.5549, 'lng': -0.1084},
        {'api_id': 49, 'name': 'Chelsea', 'city': 'London', 'country': 'England', 'code': 'GB', 'lat': 51.4817, 'lng': -0.1910},
        {'api_id': 50, 'name': 'Manchester City', 'city': 'Manchester', 'country': 'England', 'code': 'GB', 'lat': 53.4831, 'lng': -2.2004},
        {'api_id': 47, 'name': 'Tottenham', 'city': 'London', 'country': 'England', 'code': 'GB', 'lat': 51.6042, 'lng': -0.0662},
        {'api_id': 34, 'name': 'Newcastle', 'city': 'Newcastle', 'country': 'England', 'code': 'GB', 'lat': 54.9756, 'lng': -1.6217},
        {'api_id': 66, 'name': 'Aston Villa', 'city': 'Birmingham', 'country': 'England', 'code': 'GB', 'lat': 52.5092, 'lng': -1.8847},
        {'api_id': 48, 'name': 'West Ham', 'city': 'London', 'country': 'England', 'code': 'GB', 'lat': 51.5386, 'lng': -0.0166},
        {'api_id': 35, 'name': 'Brighton', 'city': 'Brighton', 'country': 'England', 'code': 'GB', 'lat': 50.8619, 'lng': -0.0839},
        {'api_id': 45, 'name': 'Everton', 'city': 'Liverpool', 'country': 'England', 'code': 'GB', 'lat': 53.4387, 'lng': -2.9664},
        {'api_id': 36, 'name': 'Fulham', 'city': 'London', 'country': 'England', 'code': 'GB', 'lat': 51.4750, 'lng': -0.2217},
        {'api_id': 52, 'name': 'Crystal Palace', 'city': 'London', 'country': 'England', 'code': 'GB', 'lat': 51.3983, 'lng': -0.0855},
        {'api_id': 55, 'name': 'Brentford', 'city': 'London', 'country': 'England', 'code': 'GB', 'lat': 51.4907, 'lng': -0.2886},
        {'api_id': 39, 'name': 'Wolves', 'city': 'Wolverhampton', 'country': 'England', 'code': 'GB', 'lat': 52.5903, 'lng': -2.1306},
        {'api_id': 65, 'name': 'Nottingham Forest', 'city': 'Nottingham', 'country': 'England', 'code': 'GB', 'lat': 52.9399, 'lng': -1.1328},
        {'api_id': 51, 'name': 'Bournemouth', 'city': 'Bournemouth', 'country': 'England', 'code': 'GB', 'lat': 50.7352, 'lng': -1.8383},
        {'api_id': 46, 'name': 'Leicester', 'city': 'Leicester', 'country': 'England', 'code': 'GB', 'lat': 52.6204, 'lng': -1.1421},
        {'api_id': 41, 'name': 'Southampton', 'city': 'Southampton', 'country': 'England', 'code': 'GB', 'lat': 50.9058, 'lng': -1.3910},
        {'api_id': 57, 'name': 'Ipswich', 'city': 'Ipswich', 'country': 'England', 'code': 'GB', 'lat': 52.0547, 'lng': 1.1447},
        
        # La Liga
        {'api_id': 541, 'name': 'Real Madrid', 'city': 'Madrid', 'country': 'Spain', 'code': 'ES', 'lat': 40.4531, 'lng': -3.6883},
        {'api_id': 529, 'name': 'Barcelona', 'city': 'Barcelona', 'country': 'Spain', 'code': 'ES', 'lat': 41.3809, 'lng': 2.1228},
        {'api_id': 530, 'name': 'Atletico Madrid', 'city': 'Madrid', 'country': 'Spain', 'code': 'ES', 'lat': 40.4362, 'lng': -3.5995},
        {'api_id': 536, 'name': 'Sevilla', 'city': 'Sevilla', 'country': 'Spain', 'code': 'ES', 'lat': 37.3840, 'lng': -5.9705},
        {'api_id': 532, 'name': 'Valencia', 'city': 'Valencia', 'country': 'Spain', 'code': 'ES', 'lat': 39.4747, 'lng': -0.3583},
        {'api_id': 533, 'name': 'Villarreal', 'city': 'Villarreal', 'country': 'Spain', 'code': 'ES', 'lat': 39.9441, 'lng': -0.1036},
        {'api_id': 548, 'name': 'Real Sociedad', 'city': 'San Sebastian', 'country': 'Spain', 'code': 'ES', 'lat': 43.3013, 'lng': -1.9737},
        {'api_id': 531, 'name': 'Athletic Bilbao', 'city': 'Bilbao', 'country': 'Spain', 'code': 'ES', 'lat': 43.2641, 'lng': -2.9494},
        {'api_id': 543, 'name': 'Real Betis', 'city': 'Sevilla', 'country': 'Spain', 'code': 'ES', 'lat': 37.3567, 'lng': -5.9817},
        
        # Serie A
        {'api_id': 489, 'name': 'AC Milan', 'city': 'Milan', 'country': 'Italy', 'code': 'IT', 'lat': 45.4781, 'lng': 9.1240},
        {'api_id': 505, 'name': 'Inter', 'city': 'Milan', 'country': 'Italy', 'code': 'IT', 'lat': 45.4781, 'lng': 9.1240},
        {'api_id': 496, 'name': 'Juventus', 'city': 'Turin', 'country': 'Italy', 'code': 'IT', 'lat': 45.1096, 'lng': 7.6413},
        {'api_id': 492, 'name': 'Napoli', 'city': 'Naples', 'country': 'Italy', 'code': 'IT', 'lat': 40.8280, 'lng': 14.1930},
        {'api_id': 487, 'name': 'Roma', 'city': 'Rome', 'country': 'Italy', 'code': 'IT', 'lat': 41.9341, 'lng': 12.4547},
        {'api_id': 488, 'name': 'Lazio', 'city': 'Rome', 'country': 'Italy', 'code': 'IT', 'lat': 41.9341, 'lng': 12.4547},
        {'api_id': 499, 'name': 'Atalanta', 'city': 'Bergamo', 'country': 'Italy', 'code': 'IT', 'lat': 45.7089, 'lng': 9.6808},
        {'api_id': 502, 'name': 'Fiorentina', 'city': 'Florence', 'country': 'Italy', 'code': 'IT', 'lat': 43.7810, 'lng': 11.2822},
        
        # Bundesliga
        {'api_id': 157, 'name': 'Bayern Munich', 'city': 'Munich', 'country': 'Germany', 'code': 'DE', 'lat': 48.2188, 'lng': 11.6247},
        {'api_id': 165, 'name': 'Borussia Dortmund', 'city': 'Dortmund', 'country': 'Germany', 'code': 'DE', 'lat': 51.4926, 'lng': 7.4519},
        {'api_id': 173, 'name': 'RB Leipzig', 'city': 'Leipzig', 'country': 'Germany', 'code': 'DE', 'lat': 51.3459, 'lng': 12.3483},
        {'api_id': 168, 'name': 'Bayer Leverkusen', 'city': 'Leverkusen', 'country': 'Germany', 'code': 'DE', 'lat': 51.0383, 'lng': 7.0022},
        {'api_id': 169, 'name': 'Eintracht Frankfurt', 'city': 'Frankfurt', 'country': 'Germany', 'code': 'DE', 'lat': 50.0686, 'lng': 8.6455},
        {'api_id': 172, 'name': 'VfB Stuttgart', 'city': 'Stuttgart', 'country': 'Germany', 'code': 'DE', 'lat': 48.7922, 'lng': 9.2320},
        
        # Ligue 1
        {'api_id': 85, 'name': 'Paris Saint Germain', 'city': 'Paris', 'country': 'France', 'code': 'FR', 'lat': 48.8414, 'lng': 2.2530},
        {'api_id': 91, 'name': 'Monaco', 'city': 'Monaco', 'country': 'Monaco', 'code': 'MC', 'lat': 43.7277, 'lng': 7.4156},
        {'api_id': 81, 'name': 'Marseille', 'city': 'Marseille', 'country': 'France', 'code': 'FR', 'lat': 43.2696, 'lng': 5.3958},
        {'api_id': 80, 'name': 'Lyon', 'city': 'Lyon', 'country': 'France', 'code': 'FR', 'lat': 45.7652, 'lng': 4.9822},
        {'api_id': 82, 'name': 'Lille', 'city': 'Lille', 'country': 'France', 'code': 'FR', 'lat': 50.6119, 'lng': 3.1305},
        
        # Other notable clubs
        {'api_id': 211, 'name': 'Benfica', 'city': 'Lisbon', 'country': 'Portugal', 'code': 'PT', 'lat': 38.7528, 'lng': -9.1847},
        {'api_id': 212, 'name': 'Porto', 'city': 'Porto', 'country': 'Portugal', 'code': 'PT', 'lat': 41.1618, 'lng': -8.5836},
        {'api_id': 194, 'name': 'Ajax', 'city': 'Amsterdam', 'country': 'Netherlands', 'code': 'NL', 'lat': 52.3142, 'lng': 4.9419},
        {'api_id': 197, 'name': 'PSV', 'city': 'Eindhoven', 'country': 'Netherlands', 'code': 'NL', 'lat': 51.4417, 'lng': 5.4675},
        {'api_id': 233, 'name': 'Sporting CP', 'city': 'Lisbon', 'country': 'Portugal', 'code': 'PT', 'lat': 38.7614, 'lng': -9.1608},
    ]
    
    added = 0
    for club in MAJOR_CLUBS:
        existing = ClubLocation.query.filter_by(club_api_id=club['api_id']).first()
        if not existing:
            location = ClubLocation(
                club_api_id=club['api_id'],
                club_name=club['name'],
                city=club['city'],
                country=club['country'],
                country_code=club['code'],
                latitude=club['lat'],
                longitude=club['lng'],
                geocode_source='manual',
                geocode_confidence=1.0,
            )
            db.session.add(location)
            added += 1
    
    db.session.commit()
    logger.info(f"Seeded {added} club locations")
    return added
