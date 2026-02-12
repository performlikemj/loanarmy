# Academy Data Audit: Chelsea & Liverpool

**Date:** 2026-02-12
**Team API IDs:** Chelsea = `49`, Liverpool = `40`
**Production API:** `https://ca-loan-army-backend.lemonmoss-23c9ec03.westus2.azurecontainerapps.io`

---

## 1. Cohort Overview

### Chelsea (team_api_id = 49)

| Cohort ID | Season | League | Total Players | Sync Status |
|-----------|--------|--------|--------------|-------------|
| 1665 | 2024 | FA Youth Cup | 22 | seeded |
| 1650 | 2024 | Premier League 2 Division One | 57 | seeded |
| 1663 | 2024 | U18 PL Championship (987) | 59 | seeded |
| 1655 | 2024 | U18 PL Championship (695) | 58 | seeded |
| 1660 | 2024 | U18 PL Championship (696) | 61 | seeded |
| 1670 | 2024 | UEFA Youth League | 41 | seeded |
| 1649 | 2023 | Premier League 2 Division One | 55 | seeded |
| 1664 | 2023 | FA Youth Cup | 23 | seeded |
| 1654 | 2023 | U18 PL Championship (695) | 54 | seeded |
| 1669 | 2023 | UEFA Youth League | 30 | seeded |
| 1662 | 2023 | U18 PL Championship (987) | 43 | seeded |
| 1659 | 2023 | U18 PL Championship (696) | 43 | seeded |
| 1668 | 2022 | UEFA Youth League | 40 | seeded |
| 1648 | 2022 | Premier League 2 Division One | 54 | seeded |
| 1661 | 2022 | U18 PL Championship (987) | 42 | seeded |
| 1658 | 2022 | U18 PL Championship (696) | 40 | seeded |
| 1653 | 2022 | U18 PL Championship (695) | 47 | seeded |
| 1652 | 2021 | U18 PL North (695) | 47 | seeded |
| 1657 | 2021 | U18 PL North (696) | 58 | seeded |
| 1667 | 2021 | UEFA Youth League | 39 | seeded |
| 1647 | 2021 | Premier League 2 Division One | 46 | seeded |
| 1656 | 2020 | U18 PL South (696) | 48 | seeded |
| 1646 | 2020 | Premier League 2 Division One | 39 | seeded |
| 1651 | 2020 | U18 PL South (695) | 29 | seeded |
| 1666 | 2020 | UEFA Youth League | 0 | **no_data** |

**Chelsea total:** 25 cohorts, 24 seeded, 1 no_data. **~1,075 total players** across all cohorts.

### Liverpool (team_api_id = 40)

| Cohort ID | Season | League | Total Players | Sync Status |
|-----------|--------|--------|--------------|-------------|
| 1720 | 2024 | UEFA Youth League | 39 | seeded |
| 1713 | 2024 | U18 PL Championship (987) | 59 | seeded |
| 1710 | 2024 | U18 PL Championship (696) | 58 | seeded |
| 1715 | 2024 | FA Youth Cup | 18 | seeded |
| 1700 | 2024 | Premier League 2 Division One | 49 | seeded |
| 1705 | 2024 | U18 PL Championship (695) | 44 | seeded |
| 1712 | 2023 | U18 PL Championship (987) | 48 | seeded |
| 1714 | 2023 | FA Youth Cup | 28 | seeded |
| 1699 | 2023 | Premier League 2 Division One | 55 | seeded |
| 1704 | 2023 | U18 PL Championship (695) | 41 | seeded |
| 1709 | 2023 | U18 PL Championship (696) | 46 | seeded |
| 1719 | 2023 | UEFA Youth League | 30 | seeded |
| 1718 | 2022 | UEFA Youth League | 43 | seeded |
| 1698 | 2022 | Premier League 2 Division One | 58 | seeded |
| 1703 | 2022 | U18 PL Championship (695) | 36 | seeded |
| 1708 | 2022 | U18 PL Championship (696) | 40 | seeded |
| 1711 | 2022 | U18 PL Championship (987) | 42 | seeded |
| 1707 | 2021 | U18 PL North (696) | 37 | seeded |
| 1717 | 2021 | UEFA Youth League | 29 | seeded |
| 1702 | 2021 | U18 PL North (695) | 55 | seeded |
| 1697 | 2021 | Premier League 2 Division One | 44 | seeded |
| 1716 | 2020 | UEFA Youth League | 0 | **no_data** |
| 1706 | 2020 | U18 PL South (696) | 40 | seeded |
| 1701 | 2020 | U18 PL South (695) | 49 | seeded |
| 1696 | 2020 | Premier League 2 Division One | 36 | seeded |

**Liverpool total:** 25 cohorts, 24 seeded, 1 no_data. **~1,024 total players** across all cohorts.

### Key Observation

Both teams have identical structure: 25 cohorts spanning 5 seasons (2020-2024) across 6 league types. UEFA Youth League 2020 returned no data for both teams. All other cohorts are in "seeded" status — **none have progressed to journey sync**.

---

## 2. Member Sync Status

### Sample Cohort: Chelsea PL2 2024 (Cohort 1650)

- **Total members:** 57
- **Journey synced:** 0/57 (0%)
- **Current status distribution:** `{null: 57}` — all members have no status
- **Sync errors:** 0
- **journeys_synced_at:** `null`

### Sample Cohort: Liverpool PL2 2024 (Cohort 1700)

- **Total members:** 49
- **Journey synced:** 0/49 (0%)
- **Current status distribution:** `{null: 49}` — all members have no status
- **Sync errors:** 0
- **journeys_synced_at:** `null`

### Sample Cohort: Chelsea PL2 2021 (Cohort 1647)

- **Total members:** 46
- **Journey synced:** 0/46 (0%)
- **Current status distribution:** `{null: 46}`
- Known first-team players present but **unclassified**

### Sample Cohort: Liverpool PL2 2021 (Cohort 1697)

- **Total members:** 44
- **Journey synced:** 0/44 (0%)
- **Current status distribution:** `{null: 44}`
- Known first-team players present but **unclassified**

### Root Cause

**Journey sync has never been executed on any cohort.** All `journeys_synced_at` fields are `null`. Without journey sync, the pipeline cannot classify players into `first_team` / `on_loan` / `released` / `academy` status. This explains the universal 0% conversion rate.

---

## 3. Big 6 Analytics Comparison

| Team | team_api_id | Cohorts | Total Players | First Team | On Loan | Released | Academy | Conv. Rate |
|------|-------------|---------|--------------|------------|---------|----------|---------|------------|
| Manchester United | 33 | 24 | 1,037 | 0 | 0 | 0 | 0 | 0.0% |
| Arsenal | 42 | 24 | 1,058 | 0 | 0 | 0 | 0 | 0.0% |
| **Chelsea** | **49** | **24** | **1,075** | **0** | **0** | **0** | **0** | **0.0%** |
| Manchester City | 50 | 24 | 1,083 | 0 | 0 | 0 | 0 | 0.0% |
| Tottenham | 47 | 24 | 956 | 0 | 0 | 0 | 0 | 0.0% |
| **Liverpool** | **40** | **24** | **1,024** | **0** | **0** | **0** | **0** | **0.0%** |

**Critical finding:** This is NOT a Chelsea/Liverpool-specific problem. **ALL Big 6 teams show zero across every metric.** The data gap is systemic — the journey sync pipeline has not been run for any team.

Note: The analytics endpoint reports 24 cohorts per team (likely excluding the 1 `no_data` cohort from each team's 25 total).

---

## 4. Known Player Spot-Check

### Chelsea

| Player | Expected Status | Found in Cohorts? | player_api_id | current_status | journey_synced | Notes |
|--------|----------------|-------------------|---------------|----------------|----------------|-------|
| Reece James | first_team | **YES** (PL2 2021, id=1647) | 19545 | null | false | Currently Chelsea captain — correctly in youth data |
| Trevoh Chalobah | first_team/on_loan | **YES** (PL2 2021, id=1647) | 19720 | null | false | Was loaned to Crystal Palace, now at Chelsea |
| Levi Colwill | first_team | **YES** (confirmed, id=152953) | 152953 | null | false | Found in Chelsea cohort data, exact cohort TBD |
| Conor Gallagher | sold (Atletico) | **NOT FOUND** | — | — | — | Likely in academy before 2020 season start |
| Mason Mount | sold (Man Utd) | **NOT FOUND** | — | — | — | Graduated before 2020 season start |

**Also notable in Chelsea PL2 2021:** C. Hudson-Odoi, X. Simons (Xavi Simons!), F. Anjorin, L. Hall, M. Sarr

### Liverpool

| Player | Expected Status | Found in Cohorts? | player_api_id | current_status | journey_synced | Notes |
|--------|----------------|-------------------|---------------|----------------|----------------|-------|
| Curtis Jones | first_team | **YES** (PL2 2021, id=1697) | 293 | null | false | Regular Liverpool first-team player |
| Harvey Elliott | first_team | **YES** (PL2 2021, id=1697) | 19035 | null | false | Regular Liverpool first-team starter |
| Stefan Bajcetic | on_loan (Salzburg) | **YES** (PL2 2021, id=1697 + multiple U18 cohorts) | 310187 | null | false | Found in 5+ cohorts across leagues |
| Jarell Quansah | first_team | **YES** (PL2 2021, id=1697) | 158698 | null | false | Liverpool first-team defender |
| Tyler Morton | on_loan/sold | **YES** (PL2 2021, id=1697) | 162590 | null | false | |
| Trent Alexander-Arnold | first_team | **NOT FOUND** | — | — | — | Graduated well before 2020 — expected |

**Also notable in Liverpool PL2 2021:** C. Bradley (Conor Bradley!), K. Gordon (Kaide Gordon), O. Beck, C. Kelleher

### Summary

The known players **ARE present** in the cohort data with correct team associations. They are simply unclassified because journey sync has never run. Players who graduated before the 2020 season start (Gallagher, Mount, Alexander-Arnold) are naturally absent.

---

## 5. TrackedPlayer Breakdown

The `TrackedPlayer` table (queried via `/api/teams/<name>/players`) has **minimal data**:

### Chelsea

| # | Player | Status | Data Source | Notes |
|---|--------|--------|-------------|-------|
| 1 | O. Hutchinson (id=284428) | **sold** | journey-sync | Sold to Nottingham Forest. Parent club apps: 26, International: Jamaica (2 caps) |

**Total Chelsea tracked players: 1**

### Liverpool

| # | Player | Status | Data Source | Notes |
|---|--------|--------|-------------|-------|
| 1 | Ethan Ennis (id=284307) | **on_loan** | journey-sync | On loan at Fleetwood Town. 25 apps, 6 goals, 2 assists. Parent club apps: 9 |

**Total Liverpool tracked players: 1**

### Interpretation

The tracked player seeding pipeline was likely only tested with a small sample. Both entries show `data_source: "journey-sync"`, confirming the journey sync mechanism works — it just hasn't been run at scale.

---

## 6. Findings & Recommendations

### Data Gaps Identified

| Issue | Severity | Scope | Root Cause |
|-------|----------|-------|------------|
| **Journey sync never executed** | CRITICAL | ALL Big 6 teams | Pipeline step not triggered post-seeding |
| All cohort members have `null` status | CRITICAL | ALL teams | Direct consequence of missing journey sync |
| Analytics show 0% across all metrics | CRITICAL | ALL teams | Depends on status classification from journey sync |
| TrackedPlayer table nearly empty | HIGH | Chelsea (1), Liverpool (1) | Tracked player seeding not run at scale |
| Pre-2020 graduates absent | LOW | Expected | Cohorts only cover seasons 2020-2024 |
| UEFA Youth League 2020 = no_data | LOW | Both teams | API-Football has no squad data for that season/competition |

### Root Cause Analysis

The cohort ingestion pipeline has **two stages**:
1. **Seeding** (COMPLETE): Discovers youth leagues, fetches squad rosters, creates `CohortMember` records
2. **Journey Sync** (NOT RUN): For each member, fetches career transfers from API-Football, classifies current status

Stage 1 completed successfully — ~1,000+ players per team across 25 cohorts, with known graduates correctly present. Stage 2 (journey sync) was interrupted — likely overwhelmed the API with ~30,000-50,000 unthrottled requests (the `RateLimiter` class existed but was never used in the Phase 2 loop).

**Code issues found:**
- `big6_seeding_service.py` Phase 2: `RateLimiter` defined but never instantiated/called
- `big6_seeding_service.py` Phase 2: journeys with `sync_error` were incorrectly marked as `journey_synced=True`
- `cohort.py` full_rebuild: Stage 3 failure aborted the entire rebuild (Stages 4-7 never ran)

### Remediation Actions

1. **Code fix applied (2026-02-12)** — Updated Full Rebuild to handle this:
   - Integrated `RateLimiter` into Phase 2 (280 req/min, 7000/day cap)
   - Graceful quota-exhausted break — saves partial progress instead of failing for all remaining players
   - Fixed bug: journeys with `sync_error` no longer marked as `journey_synced=True`
   - Stage 3 failure is now non-fatal — Stages 4-7 continue even if journey sync is partial
   - Added progress logging every 50 players
   - Re-running Full Rebuild picks up where it left off (Phase 2 filters `journey_synced == False`)

2. **Run Full Rebuild again** — With the fixes deployed, re-run the rebuild. It will:
   - Skip cohort discovery (existing cohorts detected and reused)
   - Run journey sync for all ~6,000 unsynced members (rate-limited)
   - If daily quota is hit, save progress and continue to Stages 4-7
   - May need 2-3 runs to sync all players (depending on API quota)

3. **No data changes needed for pre-2020 graduates** — Gallagher, Mount, Alexander-Arnold etc. are absent because the data starts at season 2020. This is an expected limitation, not a bug.

### Key Conclusion

**The issue is NOT missing or incorrect data — it's an incomplete pipeline.** Cohort seeding worked perfectly. The journey sync step was interrupted due to unthrottled API calls. Code fixes have been applied to make the pipeline resilient and resumable.
