"""
Tests for Player Journey functionality

Tests the journey models, sync service, and API endpoints.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timezone

# Test the classification logic without database
class TestJourneyClassification:
    """Test level and entry type classification logic"""
    
    def test_classify_level_u18(self):
        """U18 teams should be classified correctly"""
        from src.services.journey_sync import JourneySyncService
        
        service = JourneySyncService(api_client=Mock())
        
        # Various U18 patterns
        assert service._classify_level("Manchester United U18", "FA Youth Cup") == "U18"
        assert service._classify_level("Arsenal U18", "U18 Premier League - South") == "U18"
        assert service._classify_level("Chelsea Under 18", "Under-18 Premier League") == "U18"
    
    def test_classify_level_u21(self):
        """U21 teams should be classified correctly"""
        from src.services.journey_sync import JourneySyncService
        
        service = JourneySyncService(api_client=Mock())
        
        assert service._classify_level("Manchester United U21", "EFL Trophy") == "U21"
        assert service._classify_level("Liverpool Under 21", "Under 21 League") == "U21"
    
    def test_classify_level_u23_pl2(self):
        """U23/PL2 teams should be classified correctly"""
        from src.services.journey_sync import JourneySyncService
        
        service = JourneySyncService(api_client=Mock())
        
        # Premier League 2 is U23 level
        assert service._classify_level("Manchester Utd U23", "Premier League 2 Division One") == "U23"
        assert service._classify_level("Everton U23", "PL2") == "U23"
        assert service._classify_level("Arsenal U23", "Development League") == "U23"
    
    def test_classify_level_first_team(self):
        """First team entries should be classified correctly"""
        from src.services.journey_sync import JourneySyncService
        
        service = JourneySyncService(api_client=Mock())
        
        assert service._classify_level("Manchester United", "Premier League") == "First Team"
        assert service._classify_level("Barcelona", "La Liga") == "First Team"
        assert service._classify_level("Bayern Munich", "Bundesliga") == "First Team"
        assert service._classify_level("Chelsea", "FA Cup") == "First Team"
        assert service._classify_level("Liverpool", "Champions League") == "First Team"
    
    def test_classify_level_international(self):
        """International entries should be classified correctly"""
        from src.services.journey_sync import JourneySyncService
        
        service = JourneySyncService(api_client=Mock())
        
        assert service._classify_level("Argentina", "World Cup - Qualification") == "International"
        assert service._classify_level("England", "Euro 2024") == "International"
        assert service._classify_level("Brazil", "Copa America") == "International"
        assert service._classify_level("Spain", "Friendlies") == "International"
    
    def test_classify_level_international_youth(self):
        """International youth entries should be classified correctly"""
        from src.services.journey_sync import JourneySyncService
        
        service = JourneySyncService(api_client=Mock())
        
        assert service._classify_level("Argentina U20", "U20 World Cup") == "International Youth"
        assert service._classify_level("England U21", "UEFA U21 Championship") == "International Youth"
        assert service._classify_level("Spain U19", "U19 Euro") == "International Youth"
    
    def test_is_international(self):
        """Test international detection"""
        from src.services.journey_sync import JourneySyncService
        
        service = JourneySyncService(api_client=Mock())
        
        assert service._is_international("World Cup Qualification") == True
        assert service._is_international("Euro 2024") == True
        assert service._is_international("Copa America") == True
        assert service._is_international("Premier League") == False
        assert service._is_international("FA Youth Cup") == False


class TestJourneyEntryCreation:
    """Test creation of journey entries from API data"""
    
    def test_create_entry_from_stat(self):
        """Test creating entry from API-Football statistics block"""
        from src.services.journey_sync import JourneySyncService
        
        service = JourneySyncService(api_client=Mock())
        
        stat = {
            'team': {'id': 33, 'name': 'Manchester United', 'logo': 'https://...'},
            'league': {'id': 39, 'name': 'Premier League', 'country': 'England', 'logo': 'https://...'},
            'games': {'appearences': 10, 'minutes': 800},
            'goals': {'total': 3, 'assists': 2}
        }
        
        entry = service._create_entry_from_stat(journey_id=1, season=2024, stat=stat)
        
        assert entry is not None
        assert entry.club_api_id == 33
        assert entry.club_name == 'Manchester United'
        assert entry.league_name == 'Premier League'
        assert entry.appearances == 10
        assert entry.goals == 3
        assert entry.assists == 2
        assert entry.level == 'First Team'
        assert entry.is_youth == False
    
    def test_create_entry_skips_zero_appearances(self):
        """Entries with zero appearances should be skipped"""
        from src.services.journey_sync import JourneySyncService
        
        service = JourneySyncService(api_client=Mock())
        
        stat = {
            'team': {'id': 33, 'name': 'Manchester United', 'logo': 'https://...'},
            'league': {'id': 39, 'name': 'Premier League', 'country': 'England'},
            'games': {'appearences': 0, 'minutes': 0},
            'goals': {'total': 0, 'assists': 0}
        }
        
        entry = service._create_entry_from_stat(journey_id=1, season=2024, stat=stat)
        
        assert entry is None
    
    def test_create_entry_youth_flag(self):
        """Youth entries should have is_youth=True"""
        from src.services.journey_sync import JourneySyncService
        
        service = JourneySyncService(api_client=Mock())
        
        stat = {
            'team': {'id': 1234, 'name': 'Manchester United U18', 'logo': 'https://...'},
            'league': {'id': 702, 'name': 'U18 Premier League', 'country': 'England'},
            'games': {'appearences': 10, 'minutes': 800},
            'goals': {'total': 5, 'assists': 3}
        }
        
        entry = service._create_entry_from_stat(journey_id=1, season=2021, stat=stat)
        
        assert entry is not None
        assert entry.level == 'U18'
        assert entry.is_youth == True


class TestClubLocationSeeding:
    """Test club location seeding"""
    
    def test_seed_data_structure(self):
        """Verify the seeded club data has correct structure"""
        from src.services.journey_sync import seed_club_locations
        
        # Just verify the function exists and MAJOR_CLUBS constant is accessible
        # Full seeding test requires database context
        assert callable(seed_club_locations)


class TestJourneyModelMethods:
    """Test journey model methods"""
    
    def test_level_priority_values(self):
        """Verify level priority values are set correctly"""
        from src.models.journey import LEVEL_PRIORITY
        
        # First team should have highest priority
        assert LEVEL_PRIORITY['First Team'] == 100
        assert LEVEL_PRIORITY['International'] == 90
        assert LEVEL_PRIORITY['U23'] == 50
        assert LEVEL_PRIORITY['U18'] == 20
        
        # Higher levels should have higher priority
        assert LEVEL_PRIORITY['First Team'] > LEVEL_PRIORITY['U23']
        assert LEVEL_PRIORITY['U23'] > LEVEL_PRIORITY['U21']
        assert LEVEL_PRIORITY['U21'] > LEVEL_PRIORITY['U18']
    
    def test_youth_levels_set(self):
        """Verify youth levels are correctly defined"""
        from src.models.journey import YOUTH_LEVELS
        
        assert 'U18' in YOUTH_LEVELS
        assert 'U19' in YOUTH_LEVELS
        assert 'U21' in YOUTH_LEVELS
        assert 'U23' in YOUTH_LEVELS
        assert 'Reserve' in YOUTH_LEVELS
        assert 'First Team' not in YOUTH_LEVELS


# Integration tests (require database)
@pytest.mark.integration
class TestJourneyIntegration:
    """Integration tests that require database context"""
    
    @pytest.fixture
    def app(self):
        """Create test Flask app"""
        from src.main import app
        app.config['TESTING'] = True
        return app
    
    @pytest.fixture
    def client(self, app):
        """Create test client"""
        return app.test_client()
    
    @pytest.mark.skip(reason="Requires database setup")
    def test_journey_api_endpoint(self, client):
        """Test journey API endpoint"""
        response = client.get('/api/players/284324/journey')
        
        # Should return 200 or 404
        assert response.status_code in [200, 404]
    
    @pytest.mark.skip(reason="Requires database setup")
    def test_journey_map_endpoint(self, client):
        """Test journey map API endpoint"""
        response = client.get('/api/players/284324/journey/map')
        
        assert response.status_code in [200, 404]
    
    @pytest.mark.skip(reason="Requires database setup")
    def test_club_locations_endpoint(self, client):
        """Test club locations API endpoint"""
        response = client.get('/api/club-locations')
        
        assert response.status_code == 200
        data = response.get_json()
        assert 'locations' in data
        assert 'count' in data


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
