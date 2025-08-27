import os
import sys
import pytest
from flask import Flask

os.environ.setdefault('API_USE_STUB_DATA', 'true')
os.environ.setdefault('OPENAI_API_KEY', 'test')
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.agents.weekly_agent import lint_and_enrich, _display_name, get_league_localization
from src.models.league import db, LeagueLocalization


def _fake_newsletter():
    return {
        "title": "Test",
        "range": ["2022-10-03", "2022-10-09"],
        "sections": [{
            "title": "Active Loans",
            "items": [
                {
                    "player_name": "\tCharlie Gerard Richard Wellens\n",
                    "loan_team": "Oldham",
                    "week_summary": "Used as substitute in two National League draws.",
                    "stats": {"minutes": 0, "goals": 0, "assists": 0, "yellows": 0, "reds": 0},
                    "match_notes": ["Came on in 2-2 draw"],
                    "links": []
                },
                {
                    "player_name": "\u00c1lvaro Fern\u00e1ndez",
                    "loan_team": "Preston",
                    "week_summary": "Started both matches, two assists.",
                    "stats": {"minutes": 180, "goals": 0, "assists": 2, "yellows": 1, "reds": 0},
                    "match_notes": ["Assist vs West Brom", "Assist at Norwich"],
                    "links": []
                },
                {
                    "player_name": "E. Galbraith",
                    "loan_team": "Salford City",
                    "week_summary": "Scored winner at Northampton.",
                    "stats": {"minutes": 90, "goals": 1, "assists": 0, "yellows": 0, "reds": 0},
                    "match_notes": ["1-0 away win"],
                    "links": []
                }
            ]
        }]
    }


def test_display_name_strips_middle_names():
    assert _display_name("Charlie Gerard Richard Wellens") == "C. Wellens"


def test_lint_rewrites_unused_substitute_and_builds_highlights():
    news = lint_and_enrich(_fake_newsletter())

    # Minutes==0 wording
    items = news["sections"][0]["items"]
    wellens = next(i for i in items if "Wellens" in i["player_name"])
    assert "Unused substitute" in wellens["week_summary"] or "unused substitute" in wellens["week_summary"].lower()
    assert any("Unused substitute" in n or "unused substitute" in n.lower() for n in wellens["match_notes"]) 

    # Highlights choose top performers (Fernandez should be first with 2A, 180')
    assert news["highlights"][0].startswith("Á. Fernández")

    # By-numbers present and sensible
    assert news["by_numbers"]["minutes_leaders"][0]["minutes"] == 180
    ga_agg = news["by_numbers"]["ga_leaders"][0]
    assert ga_agg["g"] + ga_agg["a"] >= 2


def test_get_league_localization_known_league():
    loc = get_league_localization('Eredivisie')
    assert loc == {'country': 'NL', 'search_lang': 'nl', 'ui_lang': 'nl-NL'}


def test_get_league_localization_unknown_league():
    loc = get_league_localization('Made Up League')
    assert loc == {'country': 'GB', 'search_lang': 'en', 'ui_lang': 'en-GB'}


def test_get_league_localization_from_db():
    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)

    with app.app_context():
        db.create_all()
        db.session.add(LeagueLocalization(
            league_name='A-League',
            country='AU',
            search_lang='en',
            ui_lang='en-AU'
        ))
        db.session.commit()
        loc = get_league_localization('A-League')
        assert loc == {'country': 'AU', 'search_lang': 'en', 'ui_lang': 'en-AU'}
        db.session.remove()
        db.drop_all()
