import requests
import os
import json
from typing import Dict, List, Optional, Any
import logging
from datetime import datetime, date
import time
from collections import defaultdict
from functools import lru_cache
from itertools import chain
from src.data.transfer_windows import WINDOWS
import dotenv
dotenv.load_dotenv(dotenv.find_dotenv())

# ------------------------------------------------------------------
# 🧪 Testing filter to minimize API calls
# ------------------------------------------------------------------
ONLY_TEST_TEAM_IDS = {33}               # Manchester United

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

class APIFootballClient:
    """Client for API-Football integration."""
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv('API_FOOTBALL_KEY')
        print(f"API_FOOTBALL_KEY: {self.api_key}")
        # ------------------------------------------------------------------
        # 🔧 Stub‑data toggle – must be explicitly enabled
        # ------------------------------------------------------------------
        self.use_stub = os.getenv("API_USE_STUB_DATA", "false").lower() == "true"
        if not self.api_key and not self.use_stub:
            raise RuntimeError(
                "API_FOOTBALL_KEY is missing and API_USE_STUB_DATA is not enabled. "
                "Set API_USE_STUB_DATA=true ONLY when you want to run offline tests."
            )

        mode_env = os.getenv("API_FOOTBALL_MODE", "direct").lower()

        # Force stub mode ONLY when explicitly requested
        if self.use_stub:
            self.mode = "stub"
        else:
            self.mode = mode_env

        if self.mode == "direct":
            self.base_url = "https://v3.football.api-sports.io"
            self.headers  = {"x-apisports-key": self.api_key}
            logger.info("🔗 API‑Football mode: DIRECT (v3.football.api-sports.io)")
        elif self.mode == "rapidapi":
            self.base_url = "https://api-football-v1.p.rapidapi.com/v3"
            self.headers  = {
                "X-RapidAPI-Key":  self.api_key,
                "X-RapidAPI-Host": "api-football-v1.p.rapidapi.com"
            }
            logger.info("🔗 API‑Football mode: RAPIDAPI (api-football-v1.p.rapidapi.com)")
        elif self.mode == "stub":
            if not self.use_stub:
                raise RuntimeError(
                    "Stub mode was engaged implicitly. "
                    "Enable it explicitly by setting API_USE_STUB_DATA=true."
                )
            self.base_url = None
            self.headers  = {}
            logger.info("🔗 API‑Football mode: STUB (sample data ONLY)")
        else:
            raise ValueError(
                f"Unknown API_FOOTBALL_MODE: {mode_env}. "
                "Use 'direct', 'rapidapi', or set API_USE_STUB_DATA=true for stub mode."
            )
        # Optional policy: treat a starting XI appearance with missing minutes as 90′ played.
        self.assume_full_minutes_if_started = (
            os.getenv("ASSUME_FULL_MINUTES_IF_STARTED", "false").lower() in ("true", "1", "yes")
        )
        # Dynamic season computation - will be set based on window_key or current date
        # No longer hard-coded to 2023 season
        self.current_date = date.today()  # Keep for loan data generation
        self.current_season_start_year = None  # Will be set dynamically
        self.current_season_end_year = None    # Will be set dynamically
        self.current_season = None             # Will be set dynamically
        self.season_start_date = None          # Will be set dynamically
        self.season_end_date = None            # Will be set dynamically
        
        # Set default season based on current date if no window_key provided
        self._set_default_season_from_date()
        
        logger.info(f"Default football season: {self.current_season} ({self.season_start_date} to {self.season_end_date})")
        
        # Check team filter from environment
        # self.enable_team_filter = os.getenv("TEST_ONLY_MANU", "false").lower() == "true"
        self.enable_team_filter = False
        print(f"TEST_ONLY_MANU: {self.enable_team_filter}")
        # Log team filter status
        if self.enable_team_filter:
            logger.warning(f"🧪 TEAM FILTER ACTIVE: Only processing teams {ONLY_TEST_TEAM_IDS}")
        else:
            logger.info("🌍 Team filter disabled: Processing all teams")
        
        # European league IDs from API-Football
        self.european_leagues = {
            39: {'name': 'Premier League', 'country': 'England'},
            140: {'name': 'La Liga', 'country': 'Spain'},
            135: {'name': 'Serie A', 'country': 'Italy'},
            78: {'name': 'Bundesliga', 'country': 'Germany'},
            61: {'name': 'Ligue 1', 'country': 'France'}
        }

        # --- Local cache for team_id -> team_name look‑ups (populated lazily) ---
        self._team_name_cache: Dict[int, str] = {}
        
        # Test API connection unless explicitly skipped
        if not os.getenv("SKIP_API_HANDSHAKE") and self.mode != "stub":
            try:
                self.handshake()
                logger.info("✅ API handshake successful")
            except Exception as e:
                logger.error(f"❌ API handshake failed: {e}")
                if self.use_stub:
                    logger.warning("🔄 Falling back to stub mode because API_USE_STUB_DATA=true")
                    self.mode = "stub"
                else:
                    raise
    
    def _set_default_season_from_date(self):
        """Set default season based on current date."""
        current_year = self.current_date.year
        
        # European football season typically runs from August to May/June
        # If it's January-July, we're in the second half of the season
        # If it's August-December, we're in the first half of the season
        if self.current_date.month >= 8:  # August or later
            self.current_season_start_year = current_year
            self.current_season_end_year = current_year + 1
        else:  # January to July
            self.current_season_start_year = current_year - 1
            self.current_season_end_year = current_year
        
        self.current_season = f"{self.current_season_start_year}-{self.current_season_end_year}"
        self.season_start_date = date(self.current_season_start_year, 8, 1)
        self.season_end_date = date(self.current_season_end_year, 6, 30)
    
    def set_season_from_window_key(self, window_key: str):
        """Set current season based on window_key."""
        try:
            season_slug = window_key.split("::")[0]
            self.current_season_start_year = int(season_slug.split("-")[0])
            self.current_season_end_year = self.current_season_start_year + 1
            self.current_season = f"{self.current_season_start_year}-{self.current_season_end_year}"
            self.season_start_date = date(self.current_season_start_year, 8, 1)
            self.season_end_date = date(self.current_season_end_year, 6, 30)
            
            logger.info(f"Updated season from window_key {window_key}: {self.current_season}")
        except (ValueError, IndexError) as e:
            logger.warning(f"Failed to parse season from window_key '{window_key}': {e}")
    
    def set_season_year(self, start_year: int):
        """Set current season based on start year."""
        self.current_season_start_year = start_year
        self.current_season_end_year = start_year + 1
        self.current_season = f"{start_year}-{start_year + 1}"
        self.season_start_date = date(start_year, 8, 1)
        self.season_end_date = date(start_year + 1, 6, 30)
        logger.info(
            f"Updated season to {self.current_season} (start={self.season_start_date}, end={self.season_end_date})"
        )
            # Keep current default season
    
    def _team_filter(self, team_id: int) -> bool:
        """
        Return True if this team should be fetched, False if we want to skip it
        (used to minimise API calls while testing).
        """
        if not self.enable_team_filter:             # Normal behaviour
            return True
        is_allowed = team_id in ONLY_TEST_TEAM_IDS   # Filtered behaviour
        if not is_allowed:
            logger.debug(f"🧪 Skipping team {team_id} (not in test filter)")
        return is_allowed
    
    def handshake(self):
        """Test API connection with minimal quota cost."""
        logger.info("🤝 Testing API connection...")
        try:
            # Use status endpoint which has minimal quota cost
            status = self._make_request("status")

            # Validate payload type
            if not isinstance(status, dict):
                raise RuntimeError(f"Handshake failed - unexpected payload type: {type(status).__name__}")

            # Bubble up explicit API errors (e.g., rate limit reached)
            if status.get("errors"):
                raise RuntimeError(f"Handshake failed - API errors: {status.get('errors')}")

            # Extract response; API may return a list with a single object
            response_data = status.get("response", {})
            if isinstance(response_data, list):
                response_data = response_data[0] if response_data else {}
            if not isinstance(response_data, dict):
                response_data = {}

            account = response_data.get("account", {})
            subscription = response_data.get("subscription", {})

            # API-Football status endpoint can return results: 0 but with valid account data
            if not account or not subscription:
                raise RuntimeError(f"Handshake failed - no account/subscription data in response: {status}")

            # Check if subscription is active
            if not subscription.get("active", False):
                raise RuntimeError(f"Handshake failed - subscription not active: {subscription}")

            logger.info(
                f"✅ API handshake successful - Account: {account.get('firstname', 'Unknown')} {account.get('lastname', 'Unknown')}"
            )
            logger.info(
                f"📊 Plan: {subscription.get('plan', 'Unknown')} - Active: {subscription.get('active', False)}"
            )
            return True
            
        except Exception as e:
            logger.error(f"❌ API handshake failed: {e}")
            raise
    
    def _make_request(self, endpoint: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """Make authenticated request to API-Football."""
        logger.info(f"🏈 Making API-Football request to endpoint: {endpoint}")
        logger.info(f"📝 Request params: {params}")
        logger.info(f"🔑 API key configured: {'Yes' if self.api_key else 'No'}")

        # NOTE: The transfers endpoint does **not** accept a `season` query parameter (see API‑Football v3 docs).

        # Explicit stub usage
        if self.mode == "stub":
            if not self.use_stub:
                raise RuntimeError(
                    "Unexpected fallback to stub data. "
                    "Check API key, mode, or explicitly enable API_USE_STUB_DATA for offline tests."
                )
            logger.info("🔄 Returning sample data for endpoint '%s' (stub mode)", endpoint)
            return self._get_sample_data(endpoint, params)

        try:
            url = f"{self.base_url}/{endpoint}"
            logger.info(f"🌐 Full request URL: {url}")
            logger.info(f"📡 Request headers: {self.headers}")

            response = requests.get(url, headers=self.headers, params=params or {}, timeout=15)
            logger.info(f"📊 Response status: {response.status_code}")

            # FAIL-LOUD on auth problems
            if response.status_code == 401:
                raise RuntimeError(
                    f"API-Football auth failed (HTTP 401) for {url}. "
                    f"Check API_FOOTBALL_MODE and headers. Got: {response.text[:200]}"
                )

            response.raise_for_status()
            data = response.json()

            # FAIL-LOUD on authentication errors (API-Football returns 200 but with errors)
            if data.get("errors"):
                raise RuntimeError(
                    f"API-Football auth failed for {url}. "
                    f"Check API_FOOTBALL_MODE, headers and plan coverage. "
                    f"Errors: {data.get('errors')} - Response: {response.text[:200]}"
                )

            logger.info(f"📦 Response data keys: {list(data.keys()) if isinstance(data, dict) else 'Not a dict'}")

            # Warn if no results (might indicate plan/season coverage issues)
            results_count = data.get("results", 0)
            if results_count == 0:
                logger.warning(f"API returned 0 results for {url} params={params} - check plan coverage")

            return data

        except requests.exceptions.RequestException as e:
            logger.error(f"❌ API request failed: {e}")
            raise RuntimeError(f"API request failed for {url}: {e}")
        except Exception as e:
            logger.error(f"❌ Unexpected error: {e}")
            import traceback
            logger.error(f"❌ Traceback: {traceback.format_exc()}")
            return {'response': [], 'errors': [str(e)]}
    
    def _get_sample_data(self, endpoint: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """Return comprehensive sample data when API key is not available."""
        if endpoint == 'leagues':
            return {
                'response': [
                    {
                        'league': {
                            'id': league_id,
                            'name': info['name'],
                            'country': info['country'],
                            'logo': f'https://media.api-sports.io/football/leagues/{league_id}.png',
                            'flag': f'https://media.api-sports.io/flags/{info["country"].lower()}.svg'
                        },
                        'country': {
                            'name': info['country'],
                            'code': info['country'][:2].upper(),
                            'flag': f'https://media.api-sports.io/flags/{info["country"].lower()}.svg'
                        },
                        'seasons': [{'year': self.current_season_start_year, 'start': self.season_start_date.strftime('%Y-%m-%d'), 'end': self.season_end_date.strftime('%Y-%m-%d'), 'current': True}]
                    }
                    for league_id, info in self.european_leagues.items()
                ]
            }
        
        elif endpoint == 'teams':
            league_id = params.get('league') if params else None
            
            # Comprehensive team data for all European leagues
            all_teams_data = {
                39: [  # Premier League
                    {'id': 33, 'name': 'Manchester United', 'code': 'MUN', 'country': 'England', 'founded': 1878},
                    {'id': 40, 'name': 'Liverpool', 'code': 'LIV', 'country': 'England', 'founded': 1892},
                    {'id': 50, 'name': 'Manchester City', 'code': 'MCI', 'country': 'England', 'founded': 1880},
                    {'id': 42, 'name': 'Arsenal', 'code': 'ARS', 'country': 'England', 'founded': 1886},
                    {'id': 49, 'name': 'Chelsea', 'code': 'CHE', 'country': 'England', 'founded': 1905},
                    {'id': 47, 'name': 'Tottenham', 'code': 'TOT', 'country': 'England', 'founded': 1882},
                    {'id': 34, 'name': 'Newcastle', 'code': 'NEW', 'country': 'England', 'founded': 1892},
                    {'id': 66, 'name': 'Aston Villa', 'code': 'AVL', 'country': 'England', 'founded': 1874},
                    {'id': 48, 'name': 'West Ham', 'code': 'WHU', 'country': 'England', 'founded': 1895},
                    {'id': 35, 'name': 'Brighton', 'code': 'BHA', 'country': 'England', 'founded': 1901},
                    {'id': 39, 'name': 'Wolves', 'code': 'WOL', 'country': 'England', 'founded': 1877},
                    {'id': 36, 'name': 'Fulham', 'code': 'FUL', 'country': 'England', 'founded': 1879},
                    {'id': 52, 'name': 'Crystal Palace', 'code': 'CRY', 'country': 'England', 'founded': 1905},
                    {'id': 55, 'name': 'Brentford', 'code': 'BRE', 'country': 'England', 'founded': 1889},
                    {'id': 45, 'name': 'Everton', 'code': 'EVE', 'country': 'England', 'founded': 1878},
                    {'id': 41, 'name': 'Southampton', 'code': 'SOU', 'country': 'England', 'founded': 1885},
                    {'id': 46, 'name': 'Leicester', 'code': 'LEI', 'country': 'England', 'founded': 1884},
                    {'id': 51, 'name': 'Bournemouth', 'code': 'BOU', 'country': 'England', 'founded': 1899},
                    {'id': 65, 'name': 'Nottingham Forest', 'code': 'NFO', 'country': 'England', 'founded': 1865},
                    {'id': 1359, 'name': 'Luton', 'code': 'LUT', 'country': 'England', 'founded': 1885}
                ],
                140: [  # La Liga
                    {'id': 541, 'name': 'Real Madrid', 'code': 'RMA', 'country': 'Spain', 'founded': 1902},
                    {'id': 529, 'name': 'Barcelona', 'code': 'BAR', 'country': 'Spain', 'founded': 1899},
                    {'id': 530, 'name': 'Atletico Madrid', 'code': 'ATM', 'country': 'Spain', 'founded': 1903},
                    {'id': 548, 'name': 'Real Sociedad', 'code': 'RSO', 'country': 'Spain', 'founded': 1909},
                    {'id': 533, 'name': 'Villarreal', 'code': 'VIL', 'country': 'Spain', 'founded': 1923},
                    {'id': 532, 'name': 'Valencia', 'code': 'VAL', 'country': 'Spain', 'founded': 1919},
                    {'id': 546, 'name': 'Getafe', 'code': 'GET', 'country': 'Spain', 'founded': 1983},
                    {'id': 536, 'name': 'Sevilla', 'code': 'SEV', 'country': 'Spain', 'founded': 1890},
                    {'id': 531, 'name': 'Athletic Bilbao', 'code': 'ATH', 'country': 'Spain', 'founded': 1898},
                    {'id': 538, 'name': 'Celta Vigo', 'code': 'CEL', 'country': 'Spain', 'founded': 1923},
                    {'id': 539, 'name': 'Espanyol', 'code': 'ESP', 'country': 'Spain', 'founded': 1900},
                    {'id': 540, 'name': 'Osasuna', 'code': 'OSA', 'country': 'Spain', 'founded': 1920},
                    {'id': 543, 'name': 'Real Betis', 'code': 'BET', 'country': 'Spain', 'founded': 1907},
                    {'id': 547, 'name': 'Girona', 'code': 'GIR', 'country': 'Spain', 'founded': 1930},
                    {'id': 715, 'name': 'Granada', 'code': 'GRA', 'country': 'Spain', 'founded': 1931},
                    {'id': 797, 'name': 'Las Palmas', 'code': 'LPA', 'country': 'Spain', 'founded': 1949},
                    {'id': 798, 'name': 'Mallorca', 'code': 'MLL', 'country': 'Spain', 'founded': 1916},
                    {'id': 799, 'name': 'Rayo Vallecano', 'code': 'RAY', 'country': 'Spain', 'founded': 1924},
                    {'id': 800, 'name': 'Almeria', 'code': 'ALM', 'country': 'Spain', 'founded': 1989},
                    {'id': 801, 'name': 'Cadiz', 'code': 'CAD', 'country': 'Spain', 'founded': 1910}
                ],
                135: [  # Serie A
                    {'id': 489, 'name': 'AC Milan', 'code': 'MIL', 'country': 'Italy', 'founded': 1899},
                    {'id': 496, 'name': 'Juventus', 'code': 'JUV', 'country': 'Italy', 'founded': 1897},
                    {'id': 505, 'name': 'Inter', 'code': 'INT', 'country': 'Italy', 'founded': 1908},
                    {'id': 487, 'name': 'AS Roma', 'code': 'ROM', 'country': 'Italy', 'founded': 1927},
                    {'id': 492, 'name': 'Napoli', 'code': 'NAP', 'country': 'Italy', 'founded': 1926},
                    {'id': 488, 'name': 'Lazio', 'code': 'LAZ', 'country': 'Italy', 'founded': 1900},
                    {'id': 499, 'name': 'Atalanta', 'code': 'ATA', 'country': 'Italy', 'founded': 1907},
                    {'id': 502, 'name': 'Fiorentina', 'code': 'FIO', 'country': 'Italy', 'founded': 1926},
                    {'id': 500, 'name': 'Bologna', 'code': 'BOL', 'country': 'Italy', 'founded': 1909},
                    {'id': 486, 'name': 'Torino', 'code': 'TOR', 'country': 'Italy', 'founded': 1906},
                    {'id': 490, 'name': 'Cagliari', 'code': 'CAG', 'country': 'Italy', 'founded': 1920},
                    {'id': 494, 'name': 'Udinese', 'code': 'UDI', 'country': 'Italy', 'founded': 1896},
                    {'id': 495, 'name': 'Genoa', 'code': 'GEN', 'country': 'Italy', 'founded': 1893},
                    {'id': 497, 'name': 'Hellas Verona', 'code': 'VER', 'country': 'Italy', 'founded': 1903},
                    {'id': 498, 'name': 'Monza', 'code': 'MON', 'country': 'Italy', 'founded': 1912},
                    {'id': 503, 'name': 'Sassuolo', 'code': 'SAS', 'country': 'Italy', 'founded': 1920},
                    {'id': 504, 'name': 'Lecce', 'code': 'LEC', 'country': 'Italy', 'founded': 1908},
                    {'id': 511, 'name': 'Empoli', 'code': 'EMP', 'country': 'Italy', 'founded': 1920},
                    {'id': 514, 'name': 'Salernitana', 'code': 'SAL', 'country': 'Italy', 'founded': 1919},
                    {'id': 515, 'name': 'Frosinone', 'code': 'FRO', 'country': 'Italy', 'founded': 1928}
                ],
                78: [  # Bundesliga
                    {'id': 157, 'name': 'Bayern Munich', 'code': 'BAY', 'country': 'Germany', 'founded': 1900},
                    {'id': 165, 'name': 'Borussia Dortmund', 'code': 'BVB', 'country': 'Germany', 'founded': 1909},
                    {'id': 173, 'name': 'RB Leipzig', 'code': 'RBL', 'country': 'Germany', 'founded': 2009},
                    {'id': 168, 'name': 'Bayer Leverkusen', 'code': 'B04', 'country': 'Germany', 'founded': 1904},
                    {'id': 169, 'name': 'Eintracht Frankfurt', 'code': 'SGE', 'country': 'Germany', 'founded': 1899},
                    {'id': 172, 'name': 'VfB Stuttgart', 'code': 'VfB', 'country': 'Germany', 'founded': 1893},
                    {'id': 161, 'name': 'VfL Wolfsburg', 'code': 'WOB', 'country': 'Germany', 'founded': 1945},
                    {'id': 163, 'name': 'Borussia Monchengladbach', 'code': 'BMG', 'country': 'Germany', 'founded': 1900},
                    {'id': 164, 'name': 'Union Berlin', 'code': 'FCU', 'country': 'Germany', 'founded': 1966},
                    {'id': 170, 'name': 'FC Augsburg', 'code': 'AUG', 'country': 'Germany', 'founded': 1907},
                    {'id': 171, 'name': 'TSG Hoffenheim', 'code': 'HOF', 'country': 'Germany', 'founded': 1899},
                    {'id': 174, 'name': 'SC Freiburg', 'code': 'FRE', 'country': 'Germany', 'founded': 1904},
                    {'id': 175, 'name': 'FC Koln', 'code': 'KOL', 'country': 'Germany', 'founded': 1948},
                    {'id': 176, 'name': 'VfL Bochum', 'code': 'BOC', 'country': 'Germany', 'founded': 1848},
                    {'id': 177, 'name': 'Hertha Berlin', 'code': 'HER', 'country': 'Germany', 'founded': 1892},
                    {'id': 178, 'name': 'Mainz', 'code': 'MAI', 'country': 'Germany', 'founded': 1905},
                    {'id': 179, 'name': 'Werder Bremen', 'code': 'BRE', 'country': 'Germany', 'founded': 1899},
                    {'id': 180, 'name': 'Heidenheim', 'code': 'HEI', 'country': 'Germany', 'founded': 1846}
                ],
                61: [  # Ligue 1
                    {'id': 85, 'name': 'Paris Saint Germain', 'code': 'PSG', 'country': 'France', 'founded': 1970},
                    {'id': 91, 'name': 'Monaco', 'code': 'MON', 'country': 'France', 'founded': 1924},
                    {'id': 81, 'name': 'Marseille', 'code': 'OM', 'country': 'France', 'founded': 1899},
                    {'id': 80, 'name': 'Lyon', 'code': 'OL', 'country': 'France', 'founded': 1950},
                    {'id': 94, 'name': 'Rennes', 'code': 'REN', 'country': 'France', 'founded': 1901},
                    {'id': 84, 'name': 'Nice', 'code': 'NIC', 'country': 'France', 'founded': 1904},
                    {'id': 82, 'name': 'Lille', 'code': 'LIL', 'country': 'France', 'founded': 1944},
                    {'id': 96, 'name': 'Montpellier', 'code': 'MON', 'country': 'France', 'founded': 1974},
                    {'id': 77, 'name': 'Lens', 'code': 'LEN', 'country': 'France', 'founded': 1906},
                    {'id': 79, 'name': 'Lorient', 'code': 'LOR', 'country': 'France', 'founded': 1926},
                    {'id': 83, 'name': 'Nantes', 'code': 'NAN', 'country': 'France', 'founded': 1943},
                    {'id': 93, 'name': 'Reims', 'code': 'REI', 'country': 'France', 'founded': 1931},
                    {'id': 95, 'name': 'Strasbourg', 'code': 'STR', 'country': 'France', 'founded': 1906},
                    {'id': 97, 'name': 'Toulouse', 'code': 'TOU', 'country': 'France', 'founded': 1970},
                    {'id': 98, 'name': 'Brest', 'code': 'BRE', 'country': 'France', 'founded': 1950},
                    {'id': 99, 'name': 'Clermont', 'code': 'CLE', 'country': 'France', 'founded': 1990},
                    {'id': 100, 'name': 'Metz', 'code': 'MET', 'country': 'France', 'founded': 1932},
                    {'id': 101, 'name': 'Le Havre', 'code': 'HAV', 'country': 'France', 'founded': 1872}
                ]
            }
            
            teams_data = []
            if league_id and int(league_id) in all_teams_data:
                # Return teams for specific league
                for team in all_teams_data[int(league_id)]:
                    teams_data.append({
                        'team': {
                            'id': team['id'],
                            'name': team['name'],
                            'code': team['code'],
                            'country': team['country'],
                            'founded': team['founded'],
                            'national': False,
                            'logo': f'https://media.api-sports.io/football/teams/{team["id"]}.png'
                        },
                        'venue': {
                            'id': team['id'] + 1000,
                            'name': f'{team["name"]} Stadium',
                            'address': team['country'],
                            'city': team['country'],
                            'capacity': 50000,
                            'surface': 'grass',
                            'image': f'https://media.api-sports.io/football/venues/{team["id"] + 1000}.png'
                        }
                    })
            else:
                # Return all teams from all leagues
                for league_teams in all_teams_data.values():
                    for team in league_teams:
                        teams_data.append({
                            'team': {
                                'id': team['id'],
                                'name': team['name'],
                                'code': team['code'],
                                'country': team['country'],
                                'founded': team['founded'],
                                'national': False,
                                'logo': f'https://media.api-sports.io/football/teams/{team["id"]}.png'
                            },
                            'venue': {
                                'id': team['id'] + 1000,
                                'name': f'{team["name"]} Stadium',
                                'address': team['country'],
                                'city': team['country'],
                                'capacity': 50000,
                                'surface': 'grass',
                                'image': f'https://media.api-sports.io/football/venues/{team["id"] + 1000}.png'
                            }
                        })
            
            return {'response': teams_data}
        
        elif endpoint == 'transfers':
            # Sample transfer/loan data with realistic season-based dates
            current_date_str = self.current_date.strftime('%Y-%m-%d')
            current_datetime_str = f'{current_date_str}T00:00:00+00:00'
            
            # Loan windows: Summer (July-August) and Winter (January)
            # Since we're in August 2025, we're at the start of 2025-26 season
            # But let's show loans from the 2024-25 season that are still active
            
            # Summer 2024 loans (started July-August 2024)
            summer_loan_start = date(2024, 8, 15)  # Mid-August 2024
            winter_loan_start = date(2025, 1, 15)  # January 2025 window
            recent_loan_start = date(2025, 7, 1)   # July 2025 (pre-season)
            emergency_loan_start = date(2025, 3, 1) # Emergency loan in March
            
            return {
                'response': [
                    {
                        'player': {
                            'id': 1001,
                            'name': 'Mason Greenwood'
                        },
                        'update': current_datetime_str,
                        'transfers': [
                            {
                                'date': summer_loan_start.strftime('%Y-%m-%d'),
                                'type': 'Loan',
                                'teams': {
                                    'in': {
                                        'id': 532,
                                        'name': 'Valencia',
                                        'logo': 'https://media.api-sports.io/football/teams/532.png'
                                    },
                                    'out': {
                                        'id': 33,
                                        'name': 'Manchester United',
                                        'logo': 'https://media.api-sports.io/football/teams/33.png'
                                    }
                                }
                            }
                        ]
                    },
                    {
                        'player': {
                            'id': 1002,
                            'name': 'Jadon Sancho'
                        },
                        'update': current_datetime_str,
                        'transfers': [
                            {
                                'date': winter_loan_start.strftime('%Y-%m-%d'),
                                'type': 'Loan',
                                'teams': {
                                    'in': {
                                        'id': 165,
                                        'name': 'Borussia Dortmund',
                                        'logo': 'https://media.api-sports.io/football/teams/165.png'
                                    },
                                    'out': {
                                        'id': 33,
                                        'name': 'Manchester United',
                                        'logo': 'https://media.api-sports.io/football/teams/33.png'
                                    }
                                }
                            }
                        ]
                    },
                    {
                        'player': {
                            'id': 1003,
                            'name': 'Joao Felix'
                        },
                        'update': current_datetime_str,
                        'transfers': [
                            {
                                'date': emergency_loan_start.strftime('%Y-%m-%d'),
                                'type': 'Loan',
                                'teams': {
                                    'in': {
                                        'id': 49,
                                        'name': 'Chelsea',
                                        'logo': 'https://media.api-sports.io/football/teams/49.png'
                                    },
                                    'out': {
                                        'id': 530,
                                        'name': 'Atletico Madrid',
                                        'logo': 'https://media.api-sports.io/football/teams/530.png'
                                    }
                                }
                            }
                        ]
                    },
                    {
                        'player': {
                            'id': 1004,
                            'name': 'Ansu Fati'
                        },
                        'update': current_datetime_str,
                        'transfers': [
                            {
                                'date': recent_loan_start.strftime('%Y-%m-%d'),
                                'type': 'Loan',
                                'teams': {
                                    'in': {
                                        'id': 35,
                                        'name': 'Brighton',
                                        'logo': 'https://media.api-sports.io/football/teams/35.png'
                                    },
                                    'out': {
                                        'id': 529,
                                        'name': 'Barcelona',
                                        'logo': 'https://media.api-sports.io/football/teams/529.png'
                                    }
                                }
                            }
                        ]
                    },
                    {
                        'player': {
                            'id': 1005,
                            'name': 'Conor Gallagher'
                        },
                        'update': current_datetime_str,
                        'transfers': [
                            {
                                'date': '2024-08-01',  # Full season loan from start of 2024-25
                                'type': 'Loan',
                                'teams': {
                                    'in': {
                                        'id': 52,
                                        'name': 'Crystal Palace',
                                        'logo': 'https://media.api-sports.io/football/teams/52.png'
                                    },
                                    'out': {
                                        'id': 49,
                                        'name': 'Chelsea',
                                        'logo': 'https://media.api-sports.io/football/teams/49.png'
                                    }
                                }
                            }
                        ]
                    },
                    {
                        'player': {
                            'id': 1006,
                            'name': 'Folarin Balogun'
                        },
                        'update': current_datetime_str,
                        'transfers': [
                            {
                                'date': '2025-01-31',  # January window loan
                                'type': 'Loan',
                                'teams': {
                                    'in': {
                                        'id': 66,
                                        'name': 'Aston Villa',
                                        'logo': 'https://media.api-sports.io/football/teams/66.png'
                                    },
                                    'out': {
                                        'id': 42,
                                        'name': 'Arsenal',
                                        'logo': 'https://media.api-sports.io/football/teams/42.png'
                                    }
                                }
                            }
                        ]
                    }
                ]
            }
        
        return {'response': []}
    
    def _parse_window_key(self, window_key: str) -> tuple[date, date]:
        """
        Accepts '2024-25::SUMMER', '2023-24::WINTER', or '2023-24::FULL'.
        Returns (start, end) date objects.
        Raises ValueError on malformed input.
        """
        try:
            season, segment = window_key.split("::")
            segment = segment.upper()
        except ValueError:
            raise ValueError("window_key must be '<YYYY-YY>::<SUMMER|WINTER|FULL>'")

        if season not in WINDOWS:
            raise KeyError(f"Unknown season '{season}'")

        if segment == "FULL":
            s1, e1 = WINDOWS[season]["SUMMER"]
            s2, e2 = WINDOWS[season]["WINTER"]
            return date.fromisoformat(s1), date.fromisoformat(e2)
        elif segment in ("SUMMER", "WINTER"):
            start, end = WINDOWS[season][segment]
            return date.fromisoformat(start), date.fromisoformat(end)
        else:
            raise ValueError("segment must be SUMMER, WINTER, or FULL")
        logger.debug(
            f"🗓️ _parse_window_key → season='{season}', segment='{segment}', "
            f"start={start}, end={end}"
        )    
        
    def _in_window(self, transfer_date: str, window_key: str) -> bool:
        """
        Check if a transfer date falls within the specified window.
        
        Args:
            transfer_date: ISO format date string (YYYY-MM-DD)
            window_key: Window key like '2024-25::SUMMER'
            
        Returns:
            True if transfer date is within the window boundaries
        """
        # Guardrail for missing window_key
        if not window_key:
            logger.warning("window_key missing; defaulting to FULL current season")
            window_key = f"{self.current_season_start_year}-{str(self.current_season_start_year+1)[-2:]}::FULL"
        
        try:
            start, end = self._parse_window_key(window_key)
            d = date.fromisoformat(transfer_date)
            return start <= d <= end
        except (ValueError, KeyError) as e:
            logger.warning(f"Error checking window for date {transfer_date}, window {window_key}: {e}")
            return False

    # ---------------------------------------------------------------------
    # 🆕  Team‑name helpers
    # ---------------------------------------------------------------------
    def _prime_team_cache(self, season: int | None = None) -> None:
        """
        Populate self._team_name_cache for the given season (id -> name).
        Safe to call repeatedly; only fetches once per process.
        """
        if self._team_name_cache:
            return  # Already primed
        mapping = self.get_teams_for_season(season or self.current_season_start_year)
        # mapping comes back as {team_id: team_name}
        self._team_name_cache.update(mapping)

    def get_team_name(self, team_id: int, season: int | None = None) -> str:
        """
        Return a human‑readable team name for the given ID, falling back to the
        API if not cached. Guarantees a non‑empty string.
        """
        # Ensure the cache is primed
        self._prime_team_cache(season)
        if team_id in self._team_name_cache:
            return self._team_name_cache[team_id]

        # Fallback – direct API hit (single team)
        try:
            team_info = self.get_team_by_id(team_id, season or self.current_season_start_year)
            name = team_info.get("team", {}).get("name")
            if name:
                # Cache only genuine names to avoid polluting the cache
                self._team_name_cache[team_id] = name
                return name
            # No valid name found ‑ return placeholder **without caching**
            return f"Team {team_id}"
        except Exception:
            # Absolute fallback
            return f"Team {team_id}"
    
    def get_european_leagues(self, season: int) -> List[Dict[str, Any]]:
        """Get all European top leagues."""
        try:
            # Season parameter is now required to prevent drift with window_key
            
            logger.info(f"🏆 Fetching European leagues for season {season}")
            leagues_data = []
            for league_id in self.european_leagues.keys():
                response = self._make_request('leagues', {'id': league_id, 'season': season})
                if response.get('response'):
                    leagues_data.extend(response['response'])
            return leagues_data
        except Exception as e:
            logger.error(f"Error fetching European leagues: {e}")
            return []

    # ---------------------------------------------------------------------
    # ⚽️  Fixture & statistics helpers (weekly reports)
    # ---------------------------------------------------------------------
    def get_fixtures_for_team(self, team_id: int, season: int, start: str, end: str) -> List[Dict[str, Any]]:
        """
        Fetch fixtures for a team within a date range (YYYY‑MM‑DD).
        """
        try:
            resp = self._make_request('fixtures', {
                'team': team_id,
                'season': season,
                'from': start,
                'to': end
            })
            fixtures = resp.get('response', [])
            try:
                logger.info(
                    f"Fixtures fetched: team={team_id}, season={season}, range={start}..{end}, count={len(fixtures)}"
                )
                # Log first few fixture dates + league season to spot drift
                for fx in fixtures[:3]:
                    fid = (fx.get('fixture') or {}).get('id')
                    fdt = (fx.get('fixture') or {}).get('date')
                    lseason = (fx.get('league') or {}).get('season')
                    logger.debug(
                        f"  fx id={fid}, date={fdt}, league.season={lseason} (requested={season})"
                    )
            except Exception:
                pass
            return fixtures
        except Exception as e:
            logger.error(f"Error fetching fixtures for team {team_id}: {e}")
            return []

    def get_player_stats_for_fixture(self, player_id: int, season: int, fixture_id: int) -> Dict[str, Any]:
        """
        Fetch player stats for a specific fixture. Returns {} if not found.

        The method now prefers the dedicated `/fixtures/players` endpoint, which
        provides full per‑player statistics (minutes, goals, assists, cards, etc.).
        If that endpoint yields no data (plan/coverage limits), the previous
        line‑ups + events fallback is used.
        """
        # 1️⃣ Try the preferred `/fixtures/players` endpoint first
        team_blocks = self.get_fixture_players(fixture_id)
        try:
            logger.debug(
                f"get_player_stats_for_fixture: player={player_id}, fixture_id={fixture_id}, season={season}, team_blocks={len(team_blocks or [])}"
            )
        except Exception:
            pass
        if team_blocks:
            for team_block in team_blocks:
                for p in team_block.get('players', []):
                    pinfo = p.get('player') or {}
                    if pinfo.get('id') != player_id:
                        continue
                    statistics = p.get('statistics') or []
                    if not statistics:
                        continue
                    st = statistics[0]  # first (and usually only) statistics entry
                    games = st.get('games', {}) or {}
                    goals = st.get('goals', {}) or {}
                    cards = st.get('cards', {}) or {}

                    minutes = games.get('minutes') or 0
                    substitute_flag = games.get('substitute')
                    # Detect role from substitute flag when present
                    role = 'substitutes' if substitute_flag else 'startXI'
                    played_flag = minutes > 0 or substitute_flag is not None

                    return {
                        "statistics": [{
                            "games":   {"minutes": minutes},
                            "goals":   {"total": goals.get('total') or 0,
                                        "assists": goals.get('assists') or 0},
                            "cards":   {"yellow": cards.get('yellow') or 0,
                                        "red": cards.get('red') or 0},
                            # Pass through extra fields that may be useful downstream
                            "rating": games.get('rating'),
                            "position": games.get('position'),
                            "number": games.get('number'),
                        }],
                        "played": played_flag,
                        "role": role,
                    }
        # 2️⃣ Fallback – original line‑ups + events logic
        return self._get_player_stats_from_lineups_and_events(player_id, fixture_id)


    def _get_player_stats_from_lineups_and_events(self, player_id: int, fixture_id: int) -> Dict[str, Any]:
        """
        Legacy fallback that infers player minutes & stats from the combination of
        `/fixtures/lineups` and `/fixtures/events`. Used when `/fixtures/players`
        is not available for the requested league/plan.
        """
        lineups = self.get_fixture_lineups(fixture_id).get("response", [])
        if not lineups:
            return {}

        found_section = None  # 'startXI' or 'substitutes'
        minutes = goals_total = assists_total = yellows = reds = 0

        for lu in lineups:
            for section in ("startXI", "substitutes"):
                for entry in (lu.get(section) or []):
                    pb = (entry or {}).get("player", {}) or {}
                    if pb.get("id") != player_id:
                        continue
                    found_section = section
                    minutes = pb.get("minutes")
                    goals_total = (pb.get("goals") or {}).get("total") or 0
                    assists_total = (pb.get("goals") or {}).get("assists") or 0
                    yellows = (pb.get("cards") or {}).get("yellow") or 0
                    reds = (pb.get("cards") or {}).get("red") or 0
                    break
                if found_section:
                    break
            if found_section:
                break

        if found_section is None:
            return {}

        # If minutes missing but player started, optionally assume 90′
        if minutes is None and found_section == "startXI" and self.assume_full_minutes_if_started:
            minutes = 90
        minutes = minutes or 0

        # Enrich from events endpoint when available
        events = self.get_fixture_events(fixture_id).get("response", [])
        if events:
            goals_total += sum(
                1 for ev in events
                if ev.get("type") == "Goal" and (ev.get("player") or {}).get("id") == player_id
            )
            assists_total += sum(
                1 for ev in events
                if ev.get("type") == "Goal" and (ev.get("assist") or {}).get("id") == player_id
            )
            yellows += sum(
                1 for ev in events
                if ev.get("detail") == "Yellow Card" and (ev.get("player") or {}).get("id") == player_id
            )
            reds += sum(
                1 for ev in events
                if ev.get("detail") in ("Red Card", "Second Yellow card") and
                   (ev.get("player") or {}).get("id") == player_id
            )

        return {
            "statistics": [{
                "games": {"minutes": minutes},
                "goals": {"total": goals_total, "assists": assists_total},
                "cards": {"yellow": yellows, "red": reds},
            }],
            "played": True,
            "role": found_section,
        }
    def get_fixture_players(self, fixture_id: int, team_id: int | None = None) -> list[dict]:
        """
        Fetch per‑player statistics for a fixture (API‑Football: GET /fixtures/players).
        Optionally filter by team_id. Returns list of team blocks or [] on failure.
        """
        params = {'fixture': fixture_id}
        if team_id:
            params['team'] = team_id
        try:
            resp = self._make_request('fixtures/players', params)
            return resp.get('response', [])
        except Exception as e:
            logger.error(f"Error fetching fixture players for fixture {fixture_id}: {e}")
            return []

    def get_fixture_statistics(self, fixture_id: int) -> Dict[str, Any]:
        """
        Fetch team‑level statistics for a fixture. Returns {'response': []} if not found.
        """
        try:
            resp = self._make_request('fixtures/statistics', {'fixture': fixture_id})
            return {'response': resp.get('response', [])}
        except Exception as e:
            logger.error(f"Error fetching statistics for fixture {fixture_id}: {e}")
            return {'response': []}

    def get_fixture_lineups(self, fixture_id: int) -> Dict[str, Any]:
        """
        Fetch full line‑ups for a fixture. Returns {'response': []} if none
        (API‑Football: GET /fixtures/lineups?fixture=<id>).
        """
        try:
            resp = self._make_request('fixtures/lineups', {'fixture': fixture_id})
            return {'response': resp.get('response', [])}
        except Exception as e:
            logger.error(f"Error fetching lineups for fixture {fixture_id}: {e}")
            return {'response': []}

    def get_fixture_events(self, fixture_id: int) -> Dict[str, Any]:
        """
        Fetch play‑by‑play events for a fixture (goals, assists, cards, etc.).
        Returns {'response': []} on failure or if coverage unavailable.
        """
        try:
            resp = self._make_request('fixtures/events', {'fixture': fixture_id})
            return {"response": resp.get("response", [])}
        except Exception as e:
            logger.error(f"Error fetching events for fixture {fixture_id}: {e}")
            return {"response": []}

    # ------------------------------------------------------------------
    # 🔎  Helpers for weekly loanee summary
    # ------------------------------------------------------------------
    def _compute_fixture_result_for_team(self, fixture_row: Dict[str, Any], team_id: int) -> str:
        """
        Returns 'W', 'D', or 'L' from the perspective of team_id.
        """
        try:
            teams = fixture_row.get('teams', {})
            goals = fixture_row.get('goals', {})
            home_id = teams.get('home', {}).get('id')
            away_id = teams.get('away', {}).get('id')
            home_goals = (goals or {}).get('home', 0) or 0
            away_goals = (goals or {}).get('away', 0) or 0
            if team_id == home_id:
                if home_goals > away_goals:
                    return 'W'
                if home_goals < away_goals:
                    return 'L'
                return 'D'
            if team_id == away_id:
                if away_goals > home_goals:
                    return 'W'
                if away_goals < home_goals:
                    return 'L'
                return 'D'
            return 'D'
        except Exception:
            return 'D'

    def summarize_loanee_week(
        self,
        player_id: int,
        loan_team_id: int,
        season: int,
        week_start: date,
        week_end: date,
        *,
        include_team_stats: bool = False
    ) -> Dict[str, Any]:
        """
        Summarize a loanee's week between week_start and week_end (inclusive).
        """
        start_str, end_str = week_start.isoformat(), week_end.isoformat()

        logger.info(
            f"summarize_loanee_week: player={player_id}, loan_team={loan_team_id}, season={season}, range={start_str}..{end_str}"
        )
        fixtures = self.get_fixtures_for_team(loan_team_id, season, start_str, end_str)
        logger.info(
            f"summarize_loanee_week: fixtures_count={len(fixtures)} for team={loan_team_id}"
        )
        loan_team_name = self.get_team_name(loan_team_id, season)

        totals = {'games_played': 0, 'minutes': 0, 'goals': 0,
                  'assists': 0, 'yellows': 0, 'reds': 0}
        matches = []

        for fx in fixtures:
            fixture_id = fx.get('fixture', {}).get('id')
            if not fixture_id:
                continue
            try:
                # Inspect potential season/date drift per fixture
                fx_date = (fx.get('fixture') or {}).get('date')
                fx_league_season = (fx.get('league') or {}).get('season')
                # If API returns a league season that doesn't match the requested one, warn
                if fx_league_season is not None and fx_league_season != season:
                    logger.warning(
                        f"Fixture season drift: fixture_id={fixture_id}, league.season={fx_league_season}, requested={season}, date={fx_date}"
                    )
            except Exception:
                pass

            # Player stats for this fixture
            pstats = self.get_player_stats_for_fixture(player_id, season, fixture_id)
            played = pstats.get('played', False) if pstats else False
            player_line = {'minutes': 0, 'goals': 0, 'assists': 0,
                           'yellows': 0, 'reds': 0}

            if pstats:
                stats = pstats.get('statistics', [])
                if stats:
                    g = stats[0].get('games', {}) or {}
                    goals = stats[0].get('goals', {}) or {}
                    cards = stats[0].get('cards', {}) or {}
                    minutes = g.get('minutes', 0) or 0
                    if minutes and minutes > 0:
                        played = True
                        player_line.update({
                            'minutes': minutes,
                            'goals': goals.get('total', 0) or 0,
                            'assists': goals.get('assists', 0) or 0,
                            'yellows': cards.get('yellow', 0) or 0,
                            'reds': cards.get('red', 0) or 0
                        })
                        # Accumulate totals
                        totals['games_played'] += 1
                        totals['minutes'] += player_line['minutes']
                        totals['goals'] += player_line['goals']
                        totals['assists'] += player_line['assists']
                        totals['yellows'] += player_line['yellows']
                        totals['reds'] += player_line['reds']

            teams = fx.get('teams', {})
            home = teams.get('home', {}) or {}
            away = teams.get('away', {}) or {}
            is_home = loan_team_id == home.get('id')
            opponent = away.get('name') if is_home else home.get('name')

            match_row = {
                'fixture_id': fixture_id,
                'date': fx.get('fixture', {}).get('date'),
                'competition': fx.get('league', {}).get('name'),
                'home': is_home,
                'opponent': opponent,
                'score': fx.get('goals', {}),
                'result': self._compute_fixture_result_for_team(fx, loan_team_id),
                'played': played,
                'player': player_line,
                'role': pstats.get('role') if pstats else None,
            }

            if include_team_stats:
                stats = self.get_fixture_statistics(fixture_id)
                match_row['team_statistics'] = stats.get('response', [])

            matches.append(match_row)

        return {
            'player_id': player_id,
            'loan_team_id': loan_team_id,
            'loan_team_name': loan_team_name,
            'season': season,
            'range': [start_str, end_str],
            'totals': totals,
            'matches': matches
        }

    # ------------------------------------------------------------------
    #  🔎  WEEKLY SUMMARY OF A PARENT CLUB'S LOANEES
    # ------------------------------------------------------------------
    def summarize_parent_loans_week(
        self,
        *,
        parent_team_db_id: int,
        parent_team_api_id: int,
        season: int,
        week_start: date,
        week_end: date,
        include_team_stats: bool = False,
        db_session=None,
    ) -> Dict[str, Any]:
        """Generate match-week summaries for all active loanees of one parent club."""
        from src.models.league import LoanedPlayer, Team

        start_str, end_str = week_start.isoformat(), week_end.isoformat()
        logger.info(
            f"summarize_parent_loans_week: parent_api_id={parent_team_api_id}, season={season}, range={start_str}..{end_str}"
        )
        parent_name = self.get_team_name(parent_team_api_id, season)

        # ------------------------------------------------------------------
        # 1️⃣ Fetch active loanees for this parent from DB
        # ------------------------------------------------------------------
        loanee_rows = (
            db_session.query(LoanedPlayer)
            .filter(
                LoanedPlayer.primary_team_id == parent_team_db_id,
                LoanedPlayer.is_active.is_(True),
            )
            .all()
            if db_session
            else []
        )

        loanees, skipped_missing_team = [], 0
        for lp in loanee_rows:
            loan_team_row = db_session.query(Team).get(lp.loan_team_id)
            if not loan_team_row or not loan_team_row.team_id:
                skipped_missing_team += 1
                continue
            loanees.append(
                dict(
                    player_api_id=lp.player_id,
                    player_name=lp.player_name or "",
                    loan_team_api_id=loan_team_row.team_id,
                    loan_team_name=loan_team_row.name,
                )
            )

        # ------------------------------------------------------------------
        # 2️⃣ Summarise each loanee via API-Football
        # ------------------------------------------------------------------
        summaries: list[dict] = []
        for info in loanees:
            try:
                s = self.summarize_loanee_week(
                    player_id=info["player_api_id"],
                    loan_team_id=info["loan_team_api_id"],
                    season=season,
                    week_start=week_start,
                    week_end=week_end,
                    include_team_stats=include_team_stats,
                )
                s["player_name"] = info["player_name"]
                s["loan_team_name"] = info["loan_team_name"]
                try:
                    logger.info(
                        f"Loanee weekly summary: player={s.get('player_name')} team={s.get('loan_team_name')} matches={len(s.get('matches') or [])} totals={s.get('totals')}"
                    )
                    # Log first fixture date and league.season to spot season drift
                    if s.get('matches'):
                        m0 = s['matches'][0]
                        logger.debug(
                            f"  first_match: fixture_id={m0.get('fixture_id')} date={m0.get('date')} comp={m0.get('competition')}"
                        )
                except Exception:
                    pass
                summaries.append(s)
            except Exception as exc:
                logger.warning(f"Loanee summary failed for {info}: {exc}")

        if not loanees:
            logger.info(
                f"No active loanees for parent (DB {parent_team_db_id}, API {parent_team_api_id}). "
                f"rows={len(loanee_rows)} skipped_missing_team={skipped_missing_team}"
            )

        # ------------------------------------------------------------------
        # 3️⃣ Assemble report
        # ------------------------------------------------------------------
        return {
            "parent_team": {
                "api_id": parent_team_api_id,
                "db_id": parent_team_db_id,
                "name": parent_name,
            },
            "season": season,
            "range": [start_str, end_str],
            "loanees": summaries,
            "counts": {
                "loanees_found": len(loanees),
                "loanees_summarized": len(summaries),
                "skipped_missing_team": skipped_missing_team,
            },
        }
    
    def get_league_teams(self, league_id: int, season: int) -> List[Dict[str, Any]]:
        """Get all teams from a specific league."""
        try:                
            logger.info(f"🏟️ Fetching teams for league {league_id}")
            response = self._make_request('teams', {'league': league_id, 'season': season})
            return response.get('response', [])
        except Exception as e:
            logger.error(f"Error fetching teams for league {league_id}: {e}")
            return []
    
    def get_all_european_teams(self, season: int) -> List[Dict[str, Any]]:
        """Get all teams from European top leagues."""
        try:
            logger.info(f"🌍 Fetching all European teams for season {season}")
            all_teams = []
            for league_id in self.european_leagues.keys():
                teams = self.get_league_teams(league_id, season)
                # Add league info to each team
                for team_data in teams:
                    team_data['league_info'] = {
                        'id': league_id,
                        'name': self.european_leagues[league_id]['name'],
                        'country': self.european_leagues[league_id]['country']
                    }
                all_teams.extend(teams)
            return all_teams
        except Exception as e:
            logger.error(f"Error fetching all European teams: {e}")
            return []
    
    def get_team_transfers(self, team_id: int) -> List[Dict[str, Any]]:
        """Get transfers for a specific team (transfers endpoint has no season param)."""
        try:
            params = {'team': team_id}
            response = self._make_request('transfers', params)
            return response.get('response', [])
        except Exception as e:
            logger.error(f"Error fetching transfers for team {team_id}: {e}")
            return []


    def is_loan_transfer(self, transfer_block: dict, window_key: str) -> bool:
        """
        Check if a transfer block contains a loan within the specified window.
        
        Args:
            transfer_block: Transfer data containing 'transfers' list
            window_key: Window key like '2024-25::SUMMER' to filter by date
            
        Returns:
            True if any loan transfer exists within the specified window
        """
        if 'transfers' not in transfer_block or not transfer_block['transfers']:
            return False
        
        # Debug logging for first few calls
        debug_count = getattr(self, '_debug_loan_check_count', 0)
        if debug_count < 10:
            logger.debug(f"🔍 DEBUG is_loan_transfer #{debug_count + 1}: window_key='{window_key}', transfers_count={len(transfer_block.get('transfers', []))}")
            self._debug_loan_check_count = debug_count + 1
            
        for t in transfer_block.get("transfers", []):
            transfer_type = t.get("type", "").lower()
            transfer_date = t.get("date", "")
            
            # Debug log for first few transfers
            if debug_count < 10:
                in_window_result = self._in_window(transfer_date, window_key) if transfer_date else False
                logger.debug(f"   Transfer: date='{transfer_date}', type='{transfer_type}', in_window={in_window_result}")
            
            # Check if it's a loan type and within the specified window
            if ('loan' in transfer_type and 
                transfer_date and 
                self._in_window(transfer_date, window_key)):
                if debug_count < 10:
                    logger.debug(f"   ✅ LOAN FOUND: {transfer_date} in window {window_key}")
                    return True
        
        if debug_count < 10:
            logger.debug(f"   ❌ No loans found in window {window_key}")
        return False
    
    def get_current_loans_for_team(self, team_id: int) -> List[Dict[str, Any]]:
        """Get current active loans for a team."""
        try:
            transfers = self.get_team_transfers(team_id)
            current_loans = []
            
            for transfer in transfers:
                # Use current season as default window for current loans check
                current_window = f"{self.current_season_start_year}-{str(self.current_season_start_year+1)[-2:]}::FULL"
                if self.is_loan_transfer(transfer, current_window):
                    # Check if loan is current (this would need more sophisticated date checking)
                    current_loans.append(transfer)
            
            return current_loans
        except Exception as e:
            logger.error(f"Error fetching current loans for team {team_id}: {e}")
            return []
    
    def get_player_by_id(self, player_id: int, season: Optional[int] = None) -> Dict[str, Any]:
        """Get player information by ID with smart fallbacks.

        Tries the current season first, then walks backwards through any
        available seasons for this player. As a last resort, falls back to the
        transfers endpoint (which does not require a season) to at least obtain
        the player's name. If all API lookups fail, returns sample data.
        """
        target_season = season or self.current_season_start_year
        try:
            # 1) Try the target season directly
            resp = self._make_request('players', {'id': player_id, 'season': target_season})
            players_data = resp.get('response', [])
            if players_data:
                return players_data[0]

            # 2) Discover available seasons for this player, then try the most recent
            seasons_resp = self._make_request('players/seasons', {'player': player_id})
            seasons = seasons_resp.get('response', []) or []
            # Sort seasons descending and prefer seasons <= target_season
            seasons_sorted = sorted([int(s) for s in seasons if isinstance(s, int)], reverse=True)
            for s in seasons_sorted:
                if target_season is not None and s > int(target_season):
                    continue
                try:
                    r = self._make_request('players', {'id': player_id, 'season': s})
                    r_data = r.get('response', [])
                    if r_data:
                        logger.info(f"ℹ️ Fetched player {player_id} from fallback season {s}")
                        return r_data[0]
                except Exception:
                    # Try next season
                    continue

            # 3) Last resort: use transfers endpoint to get the player's name
            try:
                tr = self._make_request('transfers', {'player': player_id})
                t_resp = tr.get('response', []) or []
                if t_resp:
                    p = (t_resp[0] or {}).get('player', {})
                    name = p.get('name') or 'Unknown'
                    firstname = p.get('firstname')
                    lastname = p.get('lastname')
                    logger.info(f"ℹ️ Using transfers fallback name for player {player_id}: {name}")
                    return {
                        'player': {
                            'id': player_id,
                            'name': name,
                            'firstname': firstname,
                            'lastname': lastname,
                            'photo': None,
                        },
                        'statistics': []
                    }
            except Exception:
                pass

            # 4) Ultimate fallback to sample
            return self._get_sample_player_data(player_id)
        except Exception as e:
            logger.error(f"Error fetching player {player_id}: {e}")
            return self._get_sample_player_data(player_id)
    
    def get_team_by_id(self, team_id: int, season: int = None) -> Dict[str, Any]:
        """Get team information by ID from API‑Football, with multiple fallbacks."""
        try:
            # First try to get team info from teams endpoint
            params = {'id': team_id}
            response = self._make_request('teams', params)
            teams_data = response.get('response', [])
            
            if teams_data:
                # API-Football returns team data nested in response array
                team_info = teams_data[0]  # First result
                return team_info
            else:
                # If not found, try to get from league teams
                for league_id in self.european_leagues.keys():
                    league_teams = self.get_league_teams(league_id, season)
                    for team_data in league_teams:
                        if team_data.get('team', {}).get('id') == team_id:
                            return team_data

                # ------------------------------------------------------------------
                # 🔄 Final fallback: try lookup without season parameter in case the
                # season‑scoped request or Top‑5 scan missed non‑Big‑5 clubs.
                # ------------------------------------------------------------------
                try:
                    response = self._make_request('teams', {'id': team_id})
                    teams_data = response.get('response', [])
                    if teams_data:
                        return teams_data[0]  # Success without season filter
                except Exception as ex_fallback:
                    logger.debug(f"Fallback team lookup without season failed for team {team_id}: {ex_fallback}")
                
                # Return sample data if API call fails or no API key
                return {}
                
        except Exception as e:
            logger.error(f"Error fetching team {team_id}: {e}")
            return {}

    def get_team_seasons(self, team_id: int) -> Dict[str, Any]:
        """Get team information by ID from API-Football."""
        try:
            # First try to get team info from teams endpoint
            params = {'id': team_id}
            response = self._make_request('teams/seasons', params)
            seasons_data = response.get('response', [])
            
            if seasons_data:
                # API-Football returns team data nested in response array
                return seasons_data
            else:
                # Return sample data if API call fails or no API key
                return []
                
        except Exception as e:
            logger.error(f"Error fetching team {team_id}: {e}")
            return []
            
    def get_teams_for_season(self, season: int = None) -> Dict[int, str]:
        """Get all teams for a season with their names, returning a mapping of team_id -> team_name."""
        if season is None:
            season = self.current_season_start_year
            
        team_mapping = {}
        
        try:
            logger.info(f"🌍 Fetching teams for season {season}")
            # Get teams from all European leagues
            for league_id in self.european_leagues.keys():
                league_teams = self.get_league_teams(league_id, season)
                for team_data in league_teams:
                    team_info = team_data.get('team', {})
                    team_id = team_info.get('id')
                    team_name = team_info.get('name')
                    if team_id and team_name:
                        team_mapping[team_id] = team_name
            
            logger.info(f"✅ Fetched {len(team_mapping)} teams for season {season}")
            return team_mapping
            
        except Exception as e:
            logger.error(f"Error fetching teams for season {season}: {e}")
            # Return sample team mapping if API fails
            return self._get_sample_team_mapping()
    
    def get_teams_with_leagues_for_season(self, season: int = None) -> Dict[int, Dict[str, str]]:
        """Get all teams for a season with their names and league info, returning a mapping of team_id -> {team_name, league_name}."""
        if season is None:
            season = self.current_season_start_year
            
        team_data = {}
        
        try:
            # Get teams from all European leagues
            for league_id, league_info in self.european_leagues.items():
                league_teams = self.get_league_teams(league_id, season)
                for team_entry in league_teams:
                    team_info = team_entry.get('team', {})
                    team_id = team_info.get('id')
                    team_name = team_info.get('name')
                    team_code = team_info.get('code', '')
                    if team_id and team_name:
                        team_data[team_id] = {
                            'name': team_name,
                            'code': team_code,
                            'league_name': league_info['name'],
                            'league_id': league_id,
                            'country': league_info['country']
                        }
            
            logger.info(f"✅ Fetched {len(team_data)} teams with league info for season {season}")
            return team_data
            
        except Exception as e:
            logger.error(f"Error fetching teams with leagues for season {season}: {e}")
            # Return sample team mapping if API fails
            return self._get_sample_team_mapping_with_leagues()
    
    def _get_sample_team_mapping(self) -> Dict[int, str]:
        """Return sample team mapping for testing."""
        return {
            33: 'Manchester United',
            34: 'Newcastle',
            49: 'Chelsea',
            529: 'Barcelona',
            530: 'Atletico Madrid',
            532: 'Real Madrid',
        }
    
    def _get_sample_team_mapping_with_leagues(self) -> Dict[int, Dict[str, str]]:
        """Return sample team mapping with league information for testing."""
        return {
            33: {'name': 'Manchester United', 'league_name': 'Premier League', 'league_id': 39, 'country': 'England'},
            34: {'name': 'Newcastle', 'league_name': 'Premier League', 'league_id': 39, 'country': 'England'},
            49: {'name': 'Chelsea', 'league_name': 'Premier League', 'league_id': 39, 'country': 'England'},
            529: {'name': 'Barcelona', 'league_name': 'La Liga', 'league_id': 140, 'country': 'Spain'},
            530: {'name': 'Atletico Madrid', 'league_name': 'La Liga', 'league_id': 140, 'country': 'Spain'},
            532: {'name': 'Real Madrid', 'league_name': 'La Liga', 'league_id': 140, 'country': 'Spain'},
        }
    
    def _get_sample_team_data(self, team_id: int) -> Dict[str, Any]:
        """Return sample team data for testing."""
        sample_teams = {
            33: {
                'team': {
                    'id': 33,
                    'name': 'Manchester United',
                    'code': 'MUN',
                    'country': 'England',
                    'founded': 1878,
                    'national': False,
                    'logo': 'https://media.api-sports.io/football/teams/33.png'
                },
                'venue': {
                    'id': 556,
                    'name': 'Old Trafford',
                    'address': 'Sir Matt Busby Way',
                    'city': 'Manchester',
                    'capacity': 76212,
                    'surface': 'grass',
                    'image': 'https://media.api-sports.io/football/venues/556.png'
                }
            },
            529: {
                'team': {
                    'id': 529,
                    'name': 'Barcelona',
                    'code': 'BAR',
                    'country': 'Spain',
                    'founded': 1899,
                    'national': False,
                    'logo': 'https://media.api-sports.io/football/teams/529.png'
                },
                'venue': {
                    'id': 1456,
                    'name': 'Camp Nou',
                    'address': 'Carrer d\'Arístides Maillol',
                    'city': 'Barcelona',
                    'capacity': 99354,
                    'surface': 'grass',
                    'image': 'https://media.api-sports.io/football/venues/1456.png'
                }
            },
            49: {
                'team': {
                    'id': 49,
                    'name': 'Chelsea',
                    'code': 'CHE',
                    'country': 'England',
                    'founded': 1905,
                    'national': False,
                    'logo': 'https://media.api-sports.io/football/teams/49.png'
                },
                'venue': {
                    'id': 519,
                    'name': 'Stamford Bridge',
                    'address': 'Fulham Road',
                    'city': 'London',
                    'capacity': 40341,
                    'surface': 'grass',
                    'image': 'https://media.api-sports.io/football/venues/519.png'
                }
            }
        }
        
        return sample_teams.get(team_id, {
            'team': {
                'id': team_id,
                'name': f'Team {team_id}',
                'code': f'T{team_id}',
                'country': 'Unknown',
                'founded': 1900,
                'national': False,
                'logo': f'https://media.api-sports.io/football/teams/{team_id}.png'
            }
        })
    
    # ---------------------------------------------------------------------
    # 🆕  Enhanced Loan Detection Methods
    # ---------------------------------------------------------------------
    
    def _get_top5_team_ids(self, league_ids: List[int], season: int = None) -> List[int]:
        """Get all team IDs from Top-5 European leagues (filtered if test mode active)."""
        if season is None:
            season = self.current_season_start_year
        team_ids = []
        for league_id in league_ids:
            if league_id in self.european_leagues:
                try:
                    teams_data = self.get_league_teams(league_id, season)
                    for team in teams_data:
                        if 'team' in team:
                            team_id = team['team']['id']
                            if self._team_filter(team_id):
                                team_ids.append(team_id)
                except Exception as e:
                    logger.warning(f"Error fetching teams for league {league_id}: {e}")
        return team_ids
    
    @lru_cache(maxsize=1)
    def _get_top5_teams_set(self, league_ids_tuple: tuple = None, season: int = None) -> set:
        """Get cached set of Top-5 European league team IDs for fast lookup."""
        if league_ids_tuple is None:
            league_ids_tuple = tuple(self.european_leagues.keys())
        if season is None:
            season = self.current_season_start_year
        
        logger.info(f"🔍 Building TOP5_TEAMS set for leagues: {league_ids_tuple}")
        team_ids = set()
        
        for league_id in league_ids_tuple:
            if league_id in self.european_leagues:
                try:
                    teams_data = self.get_league_teams(league_id, season)
                    league_team_count = 0
                    for team in teams_data:
                        if 'team' in team:
                            team_id = team['team']['id']
                            league_team_count += 1
                            # Apply team filter if active
                            if self._team_filter(team_id):
                                team_ids.add(team_id)
                    
                    if self.enable_team_filter:
                        filtered_count = len([t for t in teams_data if 'team' in t and self._team_filter(t['team']['id'])])
                        logger.info(f"📊 League {league_id} ({self.european_leagues[league_id]['name']}): {filtered_count}/{league_team_count} teams (filtered)")
                    else:
                        logger.info(f"📊 League {league_id} ({self.european_leagues[league_id]['name']}): {league_team_count} teams")
                except Exception as e:
                    logger.warning(f"Error fetching teams for league {league_id}: {e}")
        
        if self.enable_team_filter:
            logger.info(f"✅ Built TOP5_TEAMS set with {len(team_ids)} teams total (filtered for: {ONLY_TEST_TEAM_IDS})")
        else:
            logger.info(f"✅ Built TOP5_TEAMS set with {len(team_ids)} teams total")
        
        if len(team_ids) == 0:
            logger.warning("⚠️ TOP5_TEAMS set is empty! This will filter out all loans.")
        
        return team_ids
    
    def _iter_loan_transfers(self, player_block: dict, window_key: str, season_year: int = None):
        """
        Yield dicts with accurate in/out teams for each *outgoing* Big-5 loan.
        
        Args:
            player_block: Transfer data containing 'transfers' list
            window_key: Window key like '2024-25::SUMMER'
            season_year: Season year for team name lookup
            
        Yields:
            Dict containing corrected team information for valid loans
        """
        if not player_block.get('transfers'):
            return
            
        # Get TOP5 teams set for filtering
        top5_teams = self._get_top5_teams_set(season=season_year)
        
        if not top5_teams:
            logger.warning("❌ TOP5_TEAMS set is empty! This will filter out all loans.")
            return
        
        # Show sample of Top-5 teams for debugging
        sample_teams = list(top5_teams)[:5]
        logger.info(f"🔍 Top-5 teams sample: {sample_teams} (total: {len(top5_teams)} teams)")
        
        if self.enable_team_filter:
            logger.info(f"🧪 Team filter active - only processing: {ONLY_TEST_TEAM_IDS}")
        
        valid_loans = []
        
        transfer_count = len(player_block.get("transfers", []))
        if transfer_count > 0:
            logger.debug(f"🔍 Player {player_block.get('player', {}).get('id', 'unknown')}: {transfer_count} transfers to check")
            # Show structure of first transfer for debugging
            first_transfer = player_block.get("transfers", [])[0]
            logger.debug(f"  📋 Sample transfer structure: {list(first_transfer.keys())}")
            if 'teams' in first_transfer:
                teams_structure = first_transfer['teams']
                logger.debug(f"  📋 Teams structure keys: {list(teams_structure.keys())}")
        
        loans_in_window = 0
        loans_from_big5 = 0
        
        for t in player_block.get("transfers", []):
            transfer_type = t.get("type", "").lower()
            transfer_date = t.get("date", "")
            
            if 'loan' not in (transfer_type or '').lower():
                logger.debug(f"  Skipping non-loan transfer: {transfer_type}")
                continue
                
            if not transfer_date:
                logger.debug(f"  Skipping transfer with no date")
                continue
                
            if not self._in_window(transfer_date, window_key):
                logger.debug(f"  Skipping transfer outside window: {transfer_date} not in {window_key}")
                # Also log the window bounds for debugging
                try:
                    start, end = self._parse_window_key(window_key)
                    logger.debug(f"    Window bounds: {start} to {end}")
                except Exception as e:
                    logger.debug(f"    Error parsing window: {e}")
                continue
            
            loans_in_window += 1
            logger.debug(f"  ✅ Loan in window: {transfer_date} ({transfer_type})")
                
            teams_data = t.get("teams", {})
            parent = teams_data.get("out", {})
            loanee = teams_data.get("in", {})
            
            parent_id = parent.get("id")
            loanee_id = loanee.get("id")
            
            if not parent_id or not loanee_id:
                logger.debug(f"  ❌ Missing team IDs: parent={parent_id}, loanee={loanee_id}")
                continue
                
            # Only include loans originating from Big-5 clubs
            if parent_id not in top5_teams:
                logger.debug(f"  ❌ Non-Big5 parent club: {parent_id} not in Top-5 set")
                continue
            
            loans_from_big5 += 1
            logger.debug(f"  ✅ Big-5 loan: {parent_id} → {loanee_id}")
            
            # Store loan with date for latest filtering
            valid_loans.append({
                "date": t["date"],
                "primary_team_id": parent_id,
                "primary_team_name": self.get_team_name(parent_id, season_year),
                "loan_team_id": loanee_id,
                "loan_team_name": self.get_team_name(loanee_id, season_year),
                "team_ids": f"{loanee_id},{parent_id}",  # Keep consistent with new schema: [loan, primary]
                "team_count": 2,
                "loan_confidence": 1.0,
                "transfer_date": t["date"]
            })
        
        # If multiple loans in window, keep the latest one
        if valid_loans:
            latest_loan = max(valid_loans, key=lambda x: x["date"])
            logger.debug(f"  🎯 Yielding loan: {latest_loan['primary_team_name']} → {latest_loan['loan_team_name']} on {latest_loan['date']}")
            yield latest_loan
        elif transfer_count > 0:
            logger.debug(f"  ❌ No valid loans found ({loans_in_window} in window, {loans_from_big5} from Big-5)")
    
    @lru_cache(maxsize=256)
    def _cached_transfers(self, team_id: int) -> List[Dict[str, Any]]:
        """Get team transfers with LRU caching, keyed by (team_id, season)."""
        try:
            # Season parameter is now required to prevent drift with window_key
            logger.debug(f"🔍 Fetching transfers for team {team_id} (cache miss)")
            return self.get_team_transfers(team_id)
        except Exception as e:
            logger.warning(f"Error fetching transfers for team {team_id}: {e}")
            return []
    
    # ------------------------------------------------------------------
    # Unified rate-limit helper
    # ------------------------------------------------------------------
    def _respect_ratelimit(self, headers: Dict[str, Any] | None = None):
        """Sleep based on API-Football rate-limit headers (or 0.1 s fallback)."""
        if not headers:
            time.sleep(0.1)
            return
        remaining = int(headers.get("X-RateLimit-Remaining", 100))
        if remaining < 2:
            time.sleep(10)
        elif remaining < 5:
            time.sleep(5)
        elif remaining < 10:
            time.sleep(2)
    
    def _collect_outbound_loans(self, window_key: str, parent_team_ids: List[int]) -> Dict[int, Dict[str, Any]]:
        """
        Collect outbound loans from Top-5 league clubs with corrected direction logic.
        
        Args:
            window_key: Window key like '2024-25::SUMMER'
            parent_team_ids: List of Top-5 league team IDs to check
        
        Returns:
            Dict mapping player_id to loan data with correct team directions
        """
        out: Dict[int, Dict[str, Any]] = {}
        request_count = 0
        
        # Extract season year for team name lookup
        try:
            season_slug, _ = window_key.split("::")
            season_year = int(season_slug.split("-")[0])
        except (ValueError, AttributeError):
            season_year = self.current_season_start_year
        
        logger.info(f"🔍 Collecting outbound loans from {len(parent_team_ids)} Top-5 clubs for window {window_key}")
        logger.info(f"📋 Parent team IDs to check: {parent_team_ids}")
        
        teams_checked = 0
        transfers_found = 0
        loans_found = 0
        
        for parent_id in parent_team_ids:
            # Apply team filter to reduce API calls
            if not self._team_filter(parent_id):
                continue
                
            try:
                teams_checked += 1
                # Get cached transfers for this team
                transfer_blocks = self._cached_transfers(parent_id)
                request_count += 1
                
                if transfer_blocks:
                    transfers_found += len(transfer_blocks)
                    logger.info(f"Team {parent_id}: {len(transfer_blocks)} transfer blocks")
                    
                    # Log sample transfer data for debugging
                    if transfer_blocks:
                        sample_block = transfer_blocks[0]
                        logger.info(f"📋 Sample transfer block keys: {list(sample_block.keys())}")
                        if 'transfers' in sample_block and sample_block['transfers']:
                            sample_transfer = sample_block['transfers'][0]
                            logger.info(f"📋 Sample transfer keys: {list(sample_transfer.keys())}")
                            logger.info(f"📋 Sample transfer type: {sample_transfer.get('type', 'MISSING')}")
                            logger.info(f"📋 Sample transfer date: {sample_transfer.get('date', 'MISSING')}")
                            # Show all transfers for this team to see what we have
                            logger.info(f"📋 All transfers for team {parent_id}:")
                            for i, tblock in enumerate(transfer_blocks[:3]):  # Show first 3
                                if 'transfers' in tblock:
                                    for j, t in enumerate(tblock['transfers'][:2]):  # Show first 2 transfers per block
                                        logger.info(f"     Block {i}, Transfer {j}: type='{t.get('type', 'MISSING')}', date='{t.get('date', 'MISSING')}'")
                                        if 'teams' in t:
                                            teams = t.get('teams', {})
                                            out_team = teams.get('out', {}).get('id', 'MISSING')
                                            in_team = teams.get('in', {}).get('id', 'MISSING') 
                                            logger.info(f"         Teams: {out_team} → {in_team}")
                    
                    # Check each transfer block (player transfers)
                    for tblock in transfer_blocks:
                        player_id = tblock.get('player', {}).get('id')
                        if not player_id:
                            continue
                        
                        # Use the new corrected loan detection logic
                        for loan_data in self._iter_loan_transfers(tblock, window_key, season_year):
                            loans_found += 1
                            # Only keep one loan per player (latest if multiple)
                            if player_id not in out or loan_data['transfer_date'] > out[player_id].get('transfer_date', ''):
                                out[player_id] = loan_data
                                logger.info(f"✅ DIRECT LOAN: Player {player_id} from {loan_data['primary_team_name']} → {loan_data['loan_team_name']} on {loan_data['transfer_date']}")
                else:
                    logger.debug(f"Team {parent_id}: No transfers found")
                
                # Rate limiting safeguards
                if request_count % 10 == 0:
                    self._respect_ratelimit()
                    
            except Exception as e:
                logger.warning(f"Error processing outbound loans for team {parent_id}: {e}")
                continue
        
        logger.info(f"📊 Direct loan collection summary:")
        logger.info(f"   - Teams checked: {teams_checked}")
        logger.info(f"   - Transfer blocks found: {transfers_found}")
        logger.info(f"   - Loans detected: {loans_found}")
        logger.info(f"   - Unique players with loans: {len(out)}")
        
        logger.info(f"🔍 Found {len(out)} players with outbound loans from {request_count} team transfer requests")
        return out
    
    def get_direct_loan_candidates(
            self,
            window_key: str,
            league_ids: List[int] | None = None,
            *,
            season: int | None = None,
            confidence: float = 1.0
        ):
        if league_ids is None:
            league_ids = list(self.european_leagues.keys())
        if season is None:
            try:
                season_slug = window_key.split("::")[0]
                season = int(season_slug.split("-")[0])
            except (ValueError, IndexError):
                season = self.current_season_start_year
                logger.warning(f"Failed to parse season from window_key '{window_key}', using default: {season}")
        top5_team_ids = self._get_top5_team_ids(league_ids, season)
        # Collect outbound loans with corrected direction logic
        # PATCH: do not send season to transfers endpoint
        loan_candidates = self._collect_outbound_loans(window_key, top5_team_ids)
        logger.info(f"✅ Found {len(loan_candidates)} direct loan candidates from transfer data")
        return loan_candidates
    
    def _detect_from_player_stats(self, league_ids: List[int], window_key: str, season: int) -> Dict[int, List[int]]:
        """Original detection logic using player statistics."""
        logger.info(f"🔍 Detecting multi-team players using player stats for window {window_key} (season {season})")
        player_teams = defaultdict(set)  # player_id -> set of team_ids
        if season is None:
            try:
                season_slug = window_key.split("::")[0]
                season = int(season_slug.split("-")[0])
            except (ValueError, IndexError):
                season = self.current_season_start_year
                logger.warning(f"Failed to parse season from window_key '{window_key}', using default: {season}")
        for league_id in league_ids:
            # Check coverage before crawling
            if not self._check_league_coverage(league_id, season):
                logger.warning(f"⚠️ Skipping league {league_id} - no player coverage")
                continue
                
            logger.info(f"🏆 Crawling league {league_id}: {self.european_leagues[league_id]['name']}")
            
            # If team filter is active, only process teams in filter for this league
            if self.enable_team_filter:
                logger.info(f"🧪 Team filter active: Will only process filtered teams from league {league_id}")
            
            page = 1
            
            while True:
                try:
                    resp = self._make_request('players', {
                        'league': league_id, 
                        'season': season, 
                        'page': page
                    })
                    
                    players_data = resp.get('response', [])
                    logger.info(f"📊 League {league_id} page {page}: Found {len(players_data)} players")
                    
                    if not players_data:
                        logger.info(f"📄 No more players in league {league_id}, stopping pagination")
                        break
                    
                    for player_row in players_data:
                        player_id = player_row.get('player', {}).get('id')
                        if not player_id:
                            continue
                            
                        # Check all statistics for this player in this season
                        player_stats = player_row.get('statistics', [])
                        logger.debug(f"Player {player_id} has {len(player_stats)} statistics entries")
                        
                        for stat in player_stats:
                            team_info = stat.get('team', {})
                            team_id = team_info.get('id')
                            if team_id and self._team_filter(team_id):
                                player_teams[player_id].add(team_id)
                                logger.debug(f"Added team {team_id} to player {player_id}")
                    
                    # Check pagination
                    paging = resp.get('paging', {})
                    if page >= paging.get('total', 1):
                        break
                    
                    page += 1
                    logger.info(f"📄 Processed page {page-1}, moving to page {page}")
                    
                    # Respect rate limits
                    self._respect_ratelimit(resp.get('headers', {}))
                    
                except Exception as e:
                    logger.error(f"Error crawling league {league_id}, page {page}: {e}")
                    break
        
        # Filter to only players with multiple teams
        multi_team_dict = {pid: list(teams) for pid, teams in player_teams.items() if len(teams) > 1}
        logger.info(f"✅ Found {len(multi_team_dict)} players with multi-team appearances via stats")
        return multi_team_dict
    
    def detect_multi_team_players(self, league_ids: List[int] = None, window_key: str = None, season: int = None) -> Dict[int, List[int]]:
        """
        Detect players who appear in multiple teams using merged detection approach:
        1. Original player statistics crawl
        2. New outbound loan transfer sweep
        
        Args:
            league_ids: List of league IDs to search
            window_key: Window key like '2024-25::SUMMER' (preferred)
            season: Legacy season parameter (deprecated, for backward compatibility)
        
        Returns:
            Dict mapping player_id to [loan_team_id, primary_team_id] (max 2 teams)
        """
        _ = season  # Handle backward compatibility for season parameter
        if window_key is None and season is not None:
            # Convert season to window_key format (assume FULL window)
            if season >= 2022:
                season_slug = f"{season}-{str(season + 1)[-2:]}"
                window_key = f"{season_slug}::FULL"
            else:
                # Fallback for older seasons not in our windows data
                season = season
        elif window_key is None:
            # Default to current season
            window_key = "2024-25::FULL"
        
        # Extract season year from window_key for API calls (statistics are season-based)
        try:
            season_slug, _ = window_key.split("::")
            season = int(season_slug.split("-")[0])
        except (ValueError, AttributeError):
            logger.warning(f"Invalid window_key format: {window_key}, using default season")
            season = self.current_season_start_year
            
        if league_ids is None:
            league_ids = list(self.european_leagues.keys())
        
        logger.info(f"🔍 Detecting multi-team players for window {window_key} using merged approach")
        
        # Method 1: Original player statistics detection
        multi = self._detect_from_player_stats(league_ids, window_key, season)
        
        # Method 2: New outbound loan transfer sweep
        top5_team_ids = self._get_top5_team_ids(league_ids, season)
        xfer = self._collect_outbound_loans(window_key, top5_team_ids)
        
        # Convert xfer dict to team_ids format for merging
        xfer_team_ids = {}
        for pid, loan_data in xfer.items():
            # Extract team IDs from the corrected loan data
            team_ids_str = loan_data.get('team_ids', '')
            if team_ids_str:
                team_ids = [int(tid) for tid in team_ids_str.split(',')]
                xfer_team_ids[pid] = team_ids
        
        # Merge both approaches
        combined = {}
        for pid, team_ids in chain(multi.items(), xfer_team_ids.items()):
            if pid not in combined:
                combined[pid] = []
            combined[pid].extend(team_ids)
            # Remove duplicates while preserving order, then keep first two
            seen = set()
            unique_teams = []
            for team_id in combined[pid]:
                if team_id not in seen:
                    seen.add(team_id)
                    unique_teams.append(team_id)
            combined[pid] = unique_teams[:2]  # Keep first two teams
        
        # Filter to only players with multiple teams
        final_result = {pid: teams for pid, teams in combined.items() if len(teams) > 1}
        
        logger.info(f"✅ Final merged results: {len(final_result)} players with multi-team appearances")
        logger.info(f"   - From stats: {len(multi)} players")
        logger.info(f"   - From transfers: {len(xfer)} players") 
        logger.info(f"   - Combined unique: {len(final_result)} players")
        
        return final_result
    
    def _check_league_coverage(self, league_id: int, season: int) -> bool:
        """Check if a league has player coverage before crawling."""
        try:
            response = self._make_request('leagues', {'id': league_id, 'season': season})
            leagues_data = response.get('response', [])
            
            if leagues_data:
                league_info = leagues_data[0].get('league', {})
                coverage = league_info.get('coverage', {})
                players_coverage = coverage.get('players', False)
                
                logger.info(f"🏆 League {league_id} player coverage: {players_coverage}")
                
                # For now, let's proceed with all leagues since coverage might not be reliable
                # We can always filter out empty results later
                logger.info(f"🏆 Proceeding with league {league_id} regardless of coverage status")
                return True
            
            # Default to True if coverage info not available (for backwards compatibility)
            logger.warning(f"⚠️ Could not check coverage for league {league_id}, proceeding")
            return True
            
        except Exception as e:
            logger.error(f"Error checking coverage for league {league_id}: {e}")
            # Default to True on error (for backwards compatibility)
            return True
    
    def analyze_transfer_type(self, player_id: int, multi_team_dict: Dict[int, List[int]] = None, window_key: str = None, season: int = None) -> Dict[str, Any]:
        """Analyze transfer data to determine if a player is likely on loan.
        
        ENHANCED VERSION: Fixes false positives by detecting temporary loans vs. current status.
        
        Args:
            player_id: The player to analyze
            multi_team_dict: Pre-computed dict of {player_id: [team_ids]} for multi-team players
            window_key: Window key like '2024-25::SUMMER' (preferred)
            season: Legacy season parameter (deprecated, for backward compatibility)
        """
        if season is None:
            try:
                season_slug = window_key.split("::")[0]
                season = int(season_slug.split("-")[0])
            except (ValueError, IndexError):
                season = self.current_season_start_year
                logger.warning(f"Failed to parse season from window_key '{window_key}', using default: {season}")

        try:
            # Get player transfers
            transfers_data = self.get_player_transfers(player_id)
            
            loan_indicators = []
            permanent_indicators = []
            loan_confidence = 0.0
            is_likely_loan = False
            
            # Track transfers within window for enhanced analysis
            loans_in_window = 0
            permanent_transfers_in_window = 0
            transfers_in_window = []
            
            # Analyze transfer patterns - only consider transfers within the specified window
            for transfer in transfers_data:
                transfer_info = transfer.get('transfers', [])
                
                for t in transfer_info:
                    transfer_type = t.get('type', '').lower()
                    transfer_date = t.get('date')
                    
                    # Skip transfers outside the specified window
                    if not transfer_date or not self._in_window(transfer_date, window_key):
                        continue
                    
                    # Add to window analysis
                    transfers_in_window.append((transfer_date, transfer_type))
                    
                    # ENHANCED: Use only available API-Football v3 fields
                    if transfer_type == 'loan':
                        loan_indicators.append(f"Loan transfer on {transfer_date}")
                        loan_confidence += 0.8
                        loans_in_window += 1
                        
                    elif transfer_type in ['transfer', 'free transfer']:
                        permanent_indicators.append(f"Permanent transfer on {transfer_date}")
                        loan_confidence -= 0.5  # Penalize permanent transfers
                        permanent_transfers_in_window += 1
                        
                    # Check for other transfer types that might indicate permanence
                    elif transfer_type not in ['loan']:
                        permanent_indicators.append(f"Other transfer type: {transfer_type} on {transfer_date}")
                        loan_confidence -= 0.3
            
            # ENHANCED: Multi-team analysis with temporary loan detection
            if multi_team_dict and player_id in multi_team_dict:
                team_count = len(multi_team_dict[player_id])
                loan_indicators.append(f"Appears in {team_count} teams")
                
                # CRITICAL FIX: Detect temporary loans vs. current loans
                if transfers_in_window:
                    # Sort by date and get the most recent transfer
                    transfers_in_window.sort(key=lambda x: x[0])
                    most_recent_type = transfers_in_window[-1][1]
                    
                    if most_recent_type == 'loan':
                        # Most recent transfer is a loan, but check if this is temporary
                        if permanent_transfers_in_window > 0:
                            # Has both permanent transfers and loans - suggests temporary loan
                            loan_confidence -= 0.8  # Heavy penalty for temporary loans
                            loan_indicators.append("Temporary loan detected (has permanent transfers)")
                            logger.info(f"Player {player_id}: Detected temporary loan pattern")
                        else:
                            # Only loans, no permanent transfers - likely currently on loan
                            loan_confidence += 0.7
                            loan_indicators.append("Most recent transfer is a loan")
                    else:
                        # Most recent transfer is permanent - suggests current status
                        loan_confidence -= 0.4
                        loan_indicators.append("Most recent transfer is permanent")
                else:
                    # Multi-team without transfers in window - uncertain
                    loan_confidence -= 0.4
            
            # ENHANCED: Timeline logic using only available data
            if permanent_transfers_in_window > loans_in_window:
                loan_indicators.append(f"More permanent transfers ({permanent_transfers_in_window}) than loans ({loans_in_window})")
                loan_confidence -= 0.6
            
            # Determine if likely loan
            is_likely_loan = loan_confidence >= 0.5
            
            return {
                'loan_confidence': max(0.0, min(loan_confidence, 1.0)),
                'is_likely_loan': is_likely_loan,
                'indicators': loan_indicators,
                'permanent_indicators': permanent_indicators,
                'loans_in_window': loans_in_window,
                'permanent_transfers_in_window': permanent_transfers_in_window,
                'transfers': transfers_data,
                'season': season
            }
            
        except Exception as e:
            logger.error(f"Error analyzing transfers for player {player_id}: {e}")
            return {
                'loan_confidence': 0.0,
                'is_likely_loan': False,
                'indicators': [f"Error analyzing transfers: {str(e)}"],
                'permanent_indicators': [],
                'loans_in_window': 0,
                'permanent_transfers_in_window': 0,
                'transfers': [],
                'season': season
            }
    
    def get_team_players(self, team_id: int, season: int = None) -> List[Dict[str, Any]]:
        """Get all players for a team in a specific season with pagination support."""
        if season is None:
            season = self.current_season_start_year
            
        logger.info(f"👥 Fetching all players for team {team_id}, season {season}")
        
        if not self.api_key:
            # Return sample data for testing
            return self._get_sample_team_players(team_id, season)
        
        try:
            page = 1
            all_players = []
            
            while True:
                logger.info(f"📄 Fetching page {page} for team {team_id}")
                
                response = self._make_request('players', {
                    'team': team_id,
                    'season': season,
                    'page': page
                })
                
                players_data = response.get('response', [])
                if not players_data:
                    break
                    
                all_players.extend(players_data)
                
                # Check pagination info
                paging = response.get('paging', {})
                current_page = paging.get('current', page)
                total_pages = paging.get('total', 1)
                
                logger.info(f"📊 Page {current_page} of {total_pages} - found {len(players_data)} players")
                
                if current_page >= total_pages:
                    break
                    
                page += 1
                
                # Rate limiting - respect API limits
                time.sleep(1)
            
            logger.info(f"✅ Fetched {len(all_players)} total players for team {team_id}")
            return all_players
            
        except Exception as e:
            logger.error(f"Error fetching team players: {e}")
            return self._get_sample_team_players(team_id)
    
    def get_player_transfers(self, player_id: int) -> List[Dict[str, Any]]:
        """Get transfer data for a specific player."""
        # Season parameter is now required to prevent drift with window_key
            
        logger.info(f"🔄 Fetching transfers for player {player_id}")
        
        if not self.api_key:
            # Return sample transfer data for testing
            return self._get_sample_transfers(player_id=player_id)
        
        try:
            response = self._make_request('transfers', {'player': player_id})
            
            if response.get('errors'):
                logger.warning(f"⚠️ API returned errors: {response['errors']}")
                return []
            
            transfers_data = response.get('response', [])
            logger.info(f"✅ Found {len(transfers_data)} transfer records for player {player_id}")
            return transfers_data
            
        except Exception as e:
            logger.error(f"Error fetching player transfers: {e}")
            return self._get_sample_transfers(player_id=player_id)
    
    # Upsert helper functions
    def _get_or_create_fixture(self, db_session, fx, season: int):
        from src.models.weekly import Fixture  # new module
        fixture_api_id = (fx.get('fixture') or {}).get('id')
        row = db_session.query(Fixture).filter_by(fixture_id_api=fixture_api_id).first()
        if row:
            return row
        teams = fx.get('teams', {}) or {}
        goals = fx.get('goals', {}) or {}
        home = teams.get('home') or {}
        away = teams.get('away') or {}
        row = Fixture(
            fixture_id_api=fixture_api_id,
            date_utc=((fx.get('fixture') or {}).get('date')),
            season=season,
            competition_name=((fx.get('league') or {}).get('name')),
            home_team_api_id=home.get('id'),
            away_team_api_id=away.get('id'),
            home_goals=goals.get('home') or 0,
            away_goals=goals.get('away') or 0,
            raw_json=json.dumps(fx),
        )
        db_session.add(row)
        db_session.flush()
        return row

    def _upsert_player_fixture_stats(self, db_session, fixture_pk, player_api_id, team_api_id, pstats_row):
        from src.models.weekly import FixturePlayerStats
        stats = (pstats_row or {}).get('statistics', [])
        minutes=goals=assists=yellows=reds=0
        if stats:
            g = stats[0].get('games', {}) or {}
            goals_block = stats[0].get('goals', {}) or {}
            cards = stats[0].get('cards', {}) or {}
            minutes = g.get('minutes') or 0
            goals   = goals_block.get('total') or 0
            assists = goals_block.get('assists') or 0
            yellows = cards.get('yellow') or 0
            reds    = cards.get('red') or 0

        row = db_session.query(FixturePlayerStats).filter_by(
            fixture_id=fixture_pk,
            player_api_id=player_api_id
        ).first()
        if row:
            row.team_api_id = team_api_id
            row.minutes = minutes
            row.goals = goals
            row.assists = assists
            row.yellows = yellows
            row.reds = reds
            row.raw_json = json.dumps(pstats_row or {})
        else:
            row = FixturePlayerStats(
                fixture_id=fixture_pk,
                player_api_id=player_api_id,
                team_api_id=team_api_id,
                minutes=minutes, goals=goals, assists=assists, yellows=yellows, reds=reds,
                raw_json=json.dumps(pstats_row or {})
            )
            db_session.add(row)
        db_session.flush()
        return row

    def _upsert_fixture_team_stats(self, db_session, fixture_pk, team_api_id, stats_response):
        from src.models.weekly import FixtureTeamStats
        row = db_session.query(FixtureTeamStats).filter_by(
            fixture_id=fixture_pk,
            team_api_id=team_api_id
        ).first()
        if row:
            row.stats_json = json.dumps(stats_response.get('response', []))
        else:
            row = FixtureTeamStats(
                fixture_id=fixture_pk,
                team_api_id=team_api_id,
                stats_json=json.dumps(stats_response.get('response', []))
            )
            db_session.add(row)
        db_session.flush()
        return row

    def _get_sample_transfers(self, team_id: int = None, player_id: int = None) -> List[Dict[str, Any]]:
        """
        Return sample transfer data matching API Football response structure.
        
        Based on API Football transfers endpoint response format:
        https://www.api-football.com/documentation-v3#operation/get-transfers
        """
        sample_transfers = [
            {
                'player': {
                    'id': 1001,
                    'name': 'Mason Greenwood',
                    'firstname': 'Mason',
                    'lastname': 'Greenwood',
                    'age': 22,
                    'birth': {
                        'date': '2001-10-01',
                        'place': 'Bradford',
                        'country': 'England'
                    },
                    'nationality': 'England',
                    'height': '181 cm',
                    'weight': '76 kg',
                    'injured': False,
                    'photo': 'https://media.api-sports.io/football/players/1001.png'
                },
                'update': '2023-09-01T10:30:00+00:00',
                'transfers': [
                    {
                        'date': '2022-08-15',  # Within 2022-23::FULL window (July 2022 - Jan 2023)
                        'type': 'Loan',  # Explicit loan type
                        'teams': {
                            'out': {
                                'id': 33,
                                'name': 'Manchester United',
                                'logo': 'https://media.api-sports.io/football/teams/33.png'
                            },
                            'in': {
                                'id': 50,
                                'name': 'Manchester City', 
                                'logo': 'https://media.api-sports.io/football/teams/50.png'
                            }
                        }
                    },
                    # Another loan transfer in winter window
                    {
                        'date': '2023-01-15',  # Within 2022-23::FULL window (winter window)
                        'type': 'Loan',  # Another loan type
                        'teams': {
                            'out': {
                                'id': 33,
                                'name': 'Manchester United',
                                'logo': 'https://media.api-sports.io/football/teams/33.png'
                            },
                            'in': {
                                'id': 49,
                                'name': 'Chelsea',
                                'logo': 'https://media.api-sports.io/football/teams/49.png'
                            }
                        }
                    }
                ]
            },
            {
                'player': {
                    'id': 1002,
                    'name': 'Jadon Sancho',
                    'firstname': 'Jadon',
                    'lastname': 'Sancho', 
                    'age': 24,
                    'birth': {
                        'date': '2000-03-25',
                        'place': 'London',
                        'country': 'England'
                    },
                    'nationality': 'England',
                    'height': '180 cm',
                    'weight': '76 kg',
                    'injured': False,
                    'photo': 'https://media.api-sports.io/football/players/1002.png'
                },
                'update': '2023-08-15T14:20:00+00:00',
                'transfers': [
                    {
                        'date': '2023-07-15',
                        'type': 'Free',  # Permanent transfer
                        'teams': {
                            'out': {
                                'id': 33,
                                'name': 'Manchester United',
                                'logo': 'https://media.api-sports.io/football/teams/33.png'
                            },
                            'in': {
                                'id': 49,
                                'name': 'Chelsea',
                                'logo': 'https://media.api-sports.io/football/teams/49.png'
                            }
                        }
                    }
                ]
            },
            {
                'player': {
                    'id': 1003,
                    'name': 'Marcus Rashford',
                    'firstname': 'Marcus',
                    'lastname': 'Rashford',
                    'age': 26,
                    'birth': {
                        'date': '1997-10-31',
                        'place': 'Manchester',
                        'country': 'England'
                    },
                    'nationality': 'England',
                    'height': '180 cm',
                    'weight': '70 kg',
                    'injured': False,
                    'photo': 'https://media.api-sports.io/football/players/1003.png'
                },
                'update': '2023-09-10T16:45:00+00:00',
                'transfers': [
                    {
                        'date': '2023-08-15',
                        'teams': {
                            'out': {
                                'id': 33,
                                'name': 'Manchester United',
                                'logo': 'https://media.api-sports.io/football/teams/33.png'
                            },
                            'in': {
                                'id': 157,
                                'name': 'Bayern Munich',
                                'logo': 'https://media.api-sports.io/football/teams/157.png'
                            }
                        }
                    }
                ]
            }
        ]
        
        # Filter by player_id if specified
        if player_id:
            return [t for t in sample_transfers if t['player']['id'] == player_id]
        
        # Filter by team_id if specified  
        if team_id:
            filtered = []
            for transfer_item in sample_transfers:
                for transfer in transfer_item['transfers']:
                    teams = transfer.get('teams', {})
                    if (teams.get('out', {}).get('id') == team_id or 
                        teams.get('in', {}).get('id') == team_id):
                        filtered.append(transfer_item)
                        break
            return filtered
        
        return sample_transfers
    
    def _get_sample_team_players(self, team_id: int, season: int) -> List[Dict[str, Any]]:
        """Return sample team players data for testing."""
        # Generate sample players based on team_id
        sample_players = []
        
        # Known team mappings for sample data
        team_player_mapping = {
            33: [  # Manchester United
                {'id': 1001, 'name': 'Mason Greenwood', 'position': 'Attacker'},
                {'id': 1002, 'name': 'Jadon Sancho', 'position': 'Attacker'},
                {'id': 1003, 'name': 'Anthony Martial', 'position': 'Attacker'},
                {'id': 1004, 'name': 'Marcus Rashford', 'position': 'Attacker'},
                {'id': 1005, 'name': 'Amad Diallo', 'position': 'Attacker'},
            ],
            529: [  # Barcelona
                {'id': 2001, 'name': 'Ansu Fati', 'position': 'Attacker'},
                {'id': 2002, 'name': 'Ferran Torres', 'position': 'Attacker'},
                {'id': 2003, 'name': 'Pablo Torre', 'position': 'Midfielder'},
            ],
            49: [   # Chelsea
                {'id': 3001, 'name': 'Conor Gallagher', 'position': 'Midfielder'},
                {'id': 3002, 'name': 'Armando Broja', 'position': 'Attacker'},
                {'id': 3003, 'name': 'Ian Maatsen', 'position': 'Defender'},
            ]
        }
        
        players_data = team_player_mapping.get(team_id, [
            {'id': 9001, 'name': f'Player A', 'position': 'Midfielder'},
            {'id': 9002, 'name': f'Player B', 'position': 'Attacker'},
            {'id': 9003, 'name': f'Player C', 'position': 'Defender'},
        ])
        
        for player_data in players_data:
            sample_players.append({
                'player': {
                    'id': player_data['id'],
                    'name': player_data['name'],
                    'firstname': player_data['name'].split()[0],
                    'lastname': player_data['name'].split()[-1],
                    'age': 22,
                    'birth': {
                        'date': '2002-01-01',
                        'place': 'Unknown',
                        'country': 'Unknown'
                    },
                    'nationality': 'Unknown',
                    'height': '180 cm',
                    'weight': '75 kg',
                    'injured': False,
                    'photo': f'https://media.api-sports.io/football/players/{player_data["id"]}.png'
                },
                'statistics': [{
                    'team': {'id': team_id, 'name': 'Team Name'},
                    'games': {'position': player_data['position']}
                }]
            })
            
        return sample_players
    
    def _get_sample_player_data(self, player_id: int) -> Dict[str, Any]:
        """Return sample player data for testing when API is not available."""
        # Sample players based on ID ranges
        sample_players = {
            1001: {
                'player': {
                    'id': 1001,
                    'name': 'Mason Greenwood',
                    'firstname': 'Mason',
                    'lastname': 'Greenwood',
                    'age': 22,
                    'birth': {
                        'date': '2001-10-01',
                        'place': 'Bradford',
                        'country': 'England'
                    },
                    'nationality': 'England',
                    'height': '181 cm',
                    'weight': '76 kg',
                    'injured': False,
                    'photo': 'https://media.api-sports.io/football/players/1001.png'
                },
                'statistics': [{
                    'team': {'id': 33, 'name': 'Manchester United'},
                    'games': {'position': 'Attacker'}
                }]
            },
            1002: {
                'player': {
                    'id': 1002,
                    'name': 'Jadon Sancho',
                    'firstname': 'Jadon',
                    'lastname': 'Sancho',
                    'age': 24,
                    'birth': {
                        'date': '2000-03-25',
                        'place': 'London',
                        'country': 'England'
                    },
                    'nationality': 'England',
                    'height': '180 cm',
                    'weight': '76 kg',
                    'injured': False,
                    'photo': 'https://media.api-sports.io/football/players/1002.png'
                },
                'statistics': [{
                    'team': {'id': 33, 'name': 'Manchester United'},
                    'games': {'position': 'Attacker'}
                }]
            }
        }
        
        if player_id in sample_players:
            return sample_players[player_id]
        else:
            # Generate a generic player for unknown IDs
            return {
                'player': {
                    'id': player_id,
                    'name': f'Player {player_id}',
                    'firstname': f'Player',
                    'lastname': f'{player_id}',
                    'age': 25,
                    'birth': {
                        'date': '1999-01-01',
                        'place': 'Unknown',
                        'country': 'Unknown'
                    },
                    'nationality': 'Unknown',
                    'height': '180 cm',
                    'weight': '75 kg',
                    'injured': False,
                    'photo': None
                },
                'statistics': [{
                    'team': {'id': 0, 'name': 'Unknown Team'},
                    'games': {'position': 'Unknown'}
                }]
            }
