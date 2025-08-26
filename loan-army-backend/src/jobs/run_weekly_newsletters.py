import os
from datetime import date
from src.models.league import db, Team, LoanedPlayer
from src.agents.weekly_newsletter_agent import generate_team_weekly_newsletter

def teams_with_active_loans(season: int | None = None) -> list[int]:
    q = db.session.query(Team.id).join(LoanedPlayer, LoanedPlayer.primary_team_id == Team.id)\
         .filter(LoanedPlayer.is_active.is_(True)).distinct()
    if season:
        q = q.filter(Team.season == season)
    return [t[0] for t in q.all()]

def run_for_date(target_date: date):
    # Narrow to teams with active loans; you can also choose a curated list
    team_ids = teams_with_active_loans()
    results = []
    for team_db_id in team_ids:
        try:
            out = generate_team_weekly_newsletter(team_db_id, target_date)
            results.append({"team_id": team_db_id, "newsletter_id": out["id"]})
        except Exception as e:
            results.append({"team_id": team_db_id, "error": str(e)})
    return results

if __name__ == "__main__":
    # Example: run for the most recent Monday's week
    today = date.today()
    run_for_date(today)