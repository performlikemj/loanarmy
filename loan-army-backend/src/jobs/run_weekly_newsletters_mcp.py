from datetime import date
from src.models.league import db, Team, LoanedPlayer
from src.agents.weekly_agent import generate_weekly_newsletter_with_mcp_sync

def teams_with_active_loans() -> list[int]:
    q = db.session.query(Team.id)\
        .join(LoanedPlayer, LoanedPlayer.primary_team_id == Team.id)\
        .filter(LoanedPlayer.is_active.is_(True))\
        .distinct()
    return [t[0] for t in q.all()]

def run_for_date(target: date, max_failures: int = 0):
    results = []
    failures = 0
    for team_db_id in teams_with_active_loans():
        try:
            out = generate_weekly_newsletter_with_mcp_sync(team_db_id, target)
            results.append({"team_id": team_db_id, "status": "ok", "run": out})
        except Exception as e:
            failures += 1
            results.append({"team_id": team_db_id, "status": "error", "error": str(e)})
            if max_failures == 0 or failures > max_failures:
                # Abort immediately
                raise RuntimeError(f"Aborting batch: {failures} failures so far; last={e}") from e
    return results

if __name__ == "__main__":
    today = date.today()
    run_for_date(today)