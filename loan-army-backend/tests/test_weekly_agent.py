import pytest

from src.agents.weekly_agent import lint_and_enrich, _display_name


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
    assert _display_name("Charlie Gerard Richard Wellens") == "Charlie Wellens"


def test_lint_rewrites_unused_substitute_and_builds_highlights():
    news = lint_and_enrich(_fake_newsletter())

    # Minutes==0 wording
    items = news["sections"][0]["items"]
    wellens = next(i for i in items if "Wellens" in i["player_name"])
    assert "Unused substitute" in wellens["week_summary"] or "unused substitute" in wellens["week_summary"].lower()
    assert any("Unused substitute" in n or "unused substitute" in n.lower() for n in wellens["match_notes"]) 

    # Highlights choose top performers (Fernandez should be first with 2A, 180')
    assert news["highlights"][0].startswith("Álvaro Fernández")

    # By-numbers present and sensible
    assert news["by_numbers"]["minutes_leaders"][0]["minutes"] == 180
    ga_agg = news["by_numbers"]["ga_leaders"][0]
    assert ga_agg["g"] + ga_agg["a"] >= 2
