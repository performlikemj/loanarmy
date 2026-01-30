# The Academy Watch — Implementation Directive

> Context and rationale for the refactor. Read this before starting any work.

---

## Background

### What This Project Is

"Go On Loan" is a football (soccer) platform that tracks players on loan from top clubs. It was built to:

1. Aggregate loan player stats from API-Football
2. Generate AI-assisted newsletters about their performance
3. Allow writers/journalists to add commentary and monetize via Stripe

The technical foundation is solid: Flask backend, React frontend, PostgreSQL, deployed on Azure. The data pipeline works. The newsletter system works.

### Why It Hasn't Taken Off

The product hasn't gained traction despite the underlying demand being real. Key issues:

1. **Writer recruitment failed** — The model required recruiting writers to cover each club's loan players. Nobody wants to write for a platform with zero readers. Chicken-and-egg problem.

2. **AI-only content doesn't resonate** — Users explicitly said they want "other people's voices who have watched and have an interest, not robotic summaries."

3. **Scope too narrow** — Loans are seasonal (transfer windows) and represent only part of the youth development story.

4. **Monetization premature** — Built Stripe integration for writer payments before proving anyone would pay. Complexity without value.

---

## The Pivot: The Academy Watch

### New Vision

Track the **full pathway**: Academy → Loan → First Team

Instead of recruiting writers, aggregate **community voices** — takes from Reddit, Twitter, and direct user submissions. One editor (the owner) curates and adds editorial perspective. AI provides the factual data layer; humans provide the opinions.

### Target Clubs (Initial)

- Manchester United
- Arsenal
- Chelsea

These have large fanbases, active subreddits, and fans who obsessively follow academy prospects.

### Why This Will Work

1. **Validated demand** — Reddit soccer communities constantly share loan reports and academy updates. YouTubers like "Mizu" (Man United content) have grown audiences doing exactly this.

2. **Lower barrier** — Asking fans for a 1-2 sentence take is easier than recruiting dedicated writers.

3. **Broader scope** — Academy + loans covers the full youth development story, not just transfer window activity.

4. **Authentic voices** — Community takes provide the human element AI can't replicate.

---

## Design Decisions

### 1. Preserve, Don't Rebuild

The existing codebase is substantial and functional. The UI works. The data pipeline works. The newsletter system works.

**Do not** redesign the interface or rebuild working systems. Adapt what exists. The goal is to ship quickly, not to create a perfect architecture.

### 2. Simplify Authentication

The existing email OTP system already works like a magic link. Users enter email, receive code, verify. No passwords, no registration forms.

For community submissions: require email to prevent spam, but make it frictionless. One login link, then they can submit takes.

### 3. Community Takes Over Writer Recruitment

Instead of:
- Recruiting writers → Assigning teams → Managing coverage requests → Processing payments

Do:
- Scrape Reddit for relevant takes → Let users submit directly → Curate the best ones → Feature in newsletter

The editorial voice comes from one person (the owner), not a network of writers.

### 4. Handle Data Limitations Gracefully

API-Football has limited data for youth leagues:
- ✅ Lineups (who played)
- ✅ Events (goals, assists, cards)
- ❌ Detailed stats (minutes, pass %, ratings)

For academy players, show what's available ("Played 90', scored 1") rather than empty stat cards. When a player goes on loan or debuts for the first team, full stats unlock.

### 5. Keep the Aesthetic

The current black/white design with red accents is already Athletic-inspired. Don't change it. Just update text from "Go On Loan" to "The Academy Watch."

---

## What We're Building

### For Fans

1. **Weekly newsletter** — Academy and loan player updates for their club
2. **Community takes** — Curated opinions from Reddit and fellow fans
3. **Submission form** — Easy way to share their own take on a player
4. **Player pages** — Stats + pathway timeline + community takes

### For The Editor (Owner)

1. **Curation dashboard** — Review and approve/reject community takes
2. **Reddit scraper** — Pull relevant content from club subreddits
3. **Simplified workflow** — Write commentary without complex assignment systems
4. **Newsletter generation** — AI-assisted factual content + curated takes

---

## Principles for Implementation

### 1. Minimal Viable Changes

Every change should be the smallest possible modification that achieves the goal. If you can add a column instead of creating a new table, do that. If you can modify a component instead of creating a new one, do that.

### 2. Don't Break What Works

The newsletter generation works. The player stats work. The admin dashboard works. Test after every change. If something breaks, fix it before moving on.

### 3. Reuse Existing Patterns

The codebase has established patterns:
- API calls go through `lib/api.js`
- Admin pages use `AdminLayout.jsx`
- Forms use Shadcn UI components
- Auth uses the existing OTP flow

Follow these patterns. Don't invent new ones.

### 4. Ship Incrementally

Phase 1 (remove Stripe, simplify) should result in a working app.
Phase 2 (data model) should result in a working app.
Phase 3 (community features) should result in a working app.

Each phase ships something usable. Don't save all testing for the end.

---

## Success Looks Like

### Functional Success
- A fan can subscribe to the newsletter with just their email
- A fan can submit a take on a player after verifying their email
- The editor can see all pending takes and approve/reject them
- The newsletter includes community takes alongside stats
- Reddit content can be pulled into the curation queue
- The site says "The Academy Watch" everywhere

### Product Success
- The newsletter goes out weekly with minimal editor effort
- Community takes add authentic human perspective
- The submission form actually gets submissions
- Reddit scraping surfaces relevant content automatically

### Technical Success
- No Stripe code remains (it's not needed)
- No writer recruitment complexity remains
- The app is simpler than before, not more complex
- All existing tests pass (or obsolete ones are removed)

---

## What NOT To Do

1. **Don't rename `LoanedPlayer` to `TrackedPlayer`** — Migration risk, minimal benefit. Just add columns.

2. **Don't rebuild the newsletter system** — It works. Add community takes section, don't rewrite it.

3. **Don't create a new design system** — Use existing Shadcn components and black/white theme.

4. **Don't over-engineer the Reddit scraper** — Start simple: search subreddit, pull comments mentioning player names, create pending takes. Improve later.

5. **Don't add features not in the plan** — The goal is to ship the pivot, not to build the perfect product.

---

## Files to Read First

Before starting implementation:

1. `CONTINUITY.md` — Project state
2. `AGENTS.md` — Operating protocol
3. `ledgers/ACADEMY_WATCH_MINIMAL_REFACTOR.md` — Detailed task list
4. `loan-army-frontend/src/lib/api.js` — Understand API patterns
5. `loan-army-backend/src/models/league.py` — Understand data models

---

## Questions? Ask.

If something in the plan is unclear or seems wrong, ask before implementing. It's better to clarify than to build the wrong thing.

The owner is available for questions about:
- Product decisions (what should it do?)
- Priority calls (what's more important?)
- Scope questions (is this in or out?)

---

## Let's Ship This

The foundation is solid. The vision is clear. The changes are minimal.

Build The Academy Watch.
