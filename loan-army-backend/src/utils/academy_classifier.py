"""
Academy Classifier Utility

Centralised helpers for determining a player's relationship to their
academy / parent club.  Used by:
 - JourneySyncService (journey building)
 - Seed endpoint (TrackedPlayer status derivation)
 - Any future code that needs to distinguish academy, on-loan,
   first-team, or international status.
"""

import re
from typing import Optional, Tuple

# ── regex to strip youth suffixes from club names ──────────────────────
YOUTH_SUFFIXES = re.compile(
    r'\s+(U18|U19|U21|U23|Under[\s-]?\d+|II|B|Youth|Reserve|Development)s?$',
    re.IGNORECASE,
)

# ── regex to strip age-group suffix from national team names ───────────
_NATIONAL_TEAM_AGE_SUFFIX = re.compile(r'\s+U\d{2}$')

# ── FIFA nations (used by is_national_team) ────────────────────────────
_FIFA_NATIONS = frozenset({
    'Afghanistan', 'Albania', 'Algeria', 'American Samoa', 'Andorra',
    'Angola', 'Antigua and Barbuda', 'Argentina', 'Armenia', 'Aruba',
    'Australia', 'Austria', 'Azerbaijan', 'Bahamas', 'Bahrain',
    'Bangladesh', 'Barbados', 'Belarus', 'Belgium', 'Belize', 'Benin',
    'Bermuda', 'Bhutan', 'Bolivia', 'Bosnia and Herzegovina', 'Botswana',
    'Brazil', 'Brunei', 'Bulgaria', 'Burkina Faso', 'Burundi',
    'Cambodia', 'Cameroon', 'Canada', 'Cape Verde', 'Central African Republic',
    'Chad', 'Chile', 'China', 'Chinese Taipei', 'Colombia', 'Comoros',
    'Congo', 'Costa Rica', 'Croatia', 'Cuba', 'Curacao', 'Cyprus',
    'Czech Republic', 'Czechia', 'Denmark', 'Djibouti', 'Dominica',
    'Dominican Republic', 'DR Congo', 'East Timor', 'Ecuador', 'Egypt',
    'El Salvador', 'England', 'Equatorial Guinea', 'Eritrea', 'Estonia',
    'Eswatini', 'Ethiopia', 'Faroe Islands', 'Fiji', 'Finland', 'France',
    'Gabon', 'Gambia', 'Georgia', 'Germany', 'Ghana', 'Gibraltar',
    'Greece', 'Grenada', 'Guam', 'Guatemala', 'Guinea', 'Guinea-Bissau',
    'Guyana', 'Haiti', 'Honduras', 'Hong Kong', 'Hungary', 'Iceland',
    'India', 'Indonesia', 'Iran', 'Iraq', 'Ireland', 'Israel', 'Italy',
    'Ivory Coast', 'Jamaica', 'Japan', 'Jordan', 'Kazakhstan', 'Kenya',
    'Kosovo', 'Kuwait', 'Kyrgyzstan', 'Laos', 'Latvia', 'Lebanon',
    'Lesotho', 'Liberia', 'Libya', 'Liechtenstein', 'Lithuania',
    'Luxembourg', 'Macau', 'Madagascar', 'Malawi', 'Malaysia', 'Maldives',
    'Mali', 'Malta', 'Mauritania', 'Mauritius', 'Mexico', 'Moldova',
    'Mongolia', 'Montenegro', 'Montserrat', 'Morocco', 'Mozambique',
    'Myanmar', 'Namibia', 'Nepal', 'Netherlands', 'New Caledonia',
    'New Zealand', 'Nicaragua', 'Niger', 'Nigeria', 'North Korea',
    'North Macedonia', 'Northern Ireland', 'Norway', 'Oman', 'Pakistan',
    'Palestine', 'Panama', 'Papua New Guinea', 'Paraguay', 'Peru',
    'Philippines', 'Poland', 'Portugal', 'Puerto Rico', 'Qatar',
    'Republic of Ireland', 'Romania', 'Russia', 'Rwanda', 'Saint Kitts and Nevis',
    'Saint Lucia', 'Saint Vincent and the Grenadines', 'Samoa',
    'San Marino', 'Sao Tome and Principe', 'Saudi Arabia', 'Scotland',
    'Senegal', 'Serbia', 'Seychelles', 'Sierra Leone', 'Singapore',
    'Slovakia', 'Slovenia', 'Solomon Islands', 'Somalia', 'South Africa',
    'South Korea', 'South Sudan', 'Spain', 'Sri Lanka', 'Sudan',
    'Suriname', 'Sweden', 'Switzerland', 'Syria', 'Tahiti', 'Tajikistan',
    'Tanzania', 'Thailand', 'Togo', 'Tonga', 'Trinidad and Tobago',
    'Tunisia', 'Turkey', 'Turkmenistan', 'Turks and Caicos Islands',
    'Uganda', 'Ukraine', 'United Arab Emirates', 'United States',
    'Uruguay', 'US Virgin Islands', 'Uzbekistan', 'Vanuatu', 'Venezuela',
    'Vietnam', 'Wales', 'Yemen', 'Zambia', 'Zimbabwe',
})

# ── international competition keywords ─────────────────────────────────
INTERNATIONAL_PATTERNS = [
    'world cup', 'euro', 'copa america', 'african cup', 'asian cup',
    'gold cup', 'nations league', 'friendlies', 'qualification',
    'u20 world', 'u17 world', 'olympic', 'toulon', 'maurice revello',
]

# ── levels that count as "international" ───────────────────────────────
INTERNATIONAL_LEVELS = {'International', 'International Youth'}


# ─── public helpers ────────────────────────────────────────────────────

def strip_youth_suffix(club_name: str) -> str:
    """Strip youth-team suffix to get the parent club's base name.

    >>> strip_youth_suffix('Arsenal U21')
    'Arsenal'
    >>> strip_youth_suffix('Chelsea')
    'Chelsea'
    """
    return YOUTH_SUFFIXES.sub('', club_name).strip()


def is_international_level(level: Optional[str]) -> bool:
    """Return True if the level represents international duty."""
    return (level or '') in INTERNATIONAL_LEVELS


def is_international_competition(league_name: str) -> bool:
    """Return True if the league/competition name looks international."""
    lower = league_name.lower()
    return any(p in lower for p in INTERNATIONAL_PATTERNS)


def is_national_team(club_name: Optional[str]) -> bool:
    """Return True if *club_name* looks like a national team.

    Strips an optional youth age-group suffix (e.g. "U17", "U21") then
    checks the base name against a known set of FIFA nations.

    >>> is_national_team('England U17')
    True
    >>> is_national_team('Spain')
    True
    >>> is_national_team('Arsenal')
    False
    """
    if not club_name:
        return False
    base = _NATIONAL_TEAM_AGE_SUFFIX.sub('', club_name).strip()
    return base in _FIFA_NATIONS


def is_same_club(club_name: str, parent_club_name: str) -> bool:
    """Return True if *club_name* is really the same organisation as
    *parent_club_name* (e.g. "Arsenal U21" → "Arsenal").
    """
    if not club_name or not parent_club_name:
        return False
    base = strip_youth_suffix(club_name).lower()
    parent = parent_club_name.lower()
    return base == parent


def derive_player_status(
    current_club_api_id: Optional[int],
    current_club_name: Optional[str],
    current_level: Optional[str],
    parent_api_id: int,
    parent_club_name: str,
) -> Tuple[str, Optional[int], Optional[str]]:
    """Derive (status, loan_club_api_id, loan_club_name) for a player
    relative to their parent / academy club.

    Rules (in order):
    1. International duty  → not a loan (keep academy / first_team)
    2. Same club (youth-suffix stripped) → not a loan
    3. Same API ID as parent → not a loan
    4. Different club → on_loan

    Returns:
        (status, loan_club_api_id, loan_club_name)
        where status is one of 'academy', 'first_team', 'on_loan'
    """
    # No current club info → assume still at academy
    if not current_club_api_id:
        return ('academy', None, None)

    # 1. International duty is never a loan
    if is_international_level(current_level):
        return (_base_status(current_level), None, None)

    # 1b. National team club name is never a loan
    if is_national_team(current_club_name):
        return (_base_status(current_level), None, None)

    # 2. Same API ID → player at the parent club itself
    if current_club_api_id == parent_api_id:
        return (_base_status(current_level), None, None)

    # 3. Same club with youth suffix (e.g. "Arsenal U21" for Arsenal)
    if is_same_club(current_club_name or '', parent_club_name):
        return (_base_status(current_level), None, None)

    # 4. Genuinely at a different club → on loan
    return ('on_loan', current_club_api_id, current_club_name)


# ─── internal ──────────────────────────────────────────────────────────

def _base_status(current_level: Optional[str]) -> str:
    """Pick 'first_team' or 'academy' based on the player's current level."""
    if current_level == 'First Team':
        return 'first_team'
    return 'academy'
