#!/bin/bash
# Setup script for AGENTS.md + Ralph workflow
# Run this in your project root: ./setup-agents.sh

set -e

echo "Setting up AGENTS.md + Ralph workflow..."

# Create directories
mkdir -p ledgers/archive
mkdir -p scripts/ralph

echo "Created directories"

# Detect project stack
detect_stack() {
  if [ -f "package.json" ]; then
    if [ -f "pnpm-lock.yaml" ]; then
      echo "pnpm"
    elif [ -f "yarn.lock" ]; then
      echo "yarn"
    else
      echo "npm"
    fi
  elif [ -f "requirements.txt" ] || [ -f "pyproject.toml" ]; then
    echo "python"
  elif [ -f "Cargo.toml" ]; then
    echo "rust"
  elif [ -f "go.mod" ]; then
    echo "go"
  else
    echo "unknown"
  fi
}

STACK=$(detect_stack)
echo "Detected stack: $STACK"

# Set default commands based on stack
case $STACK in
  pnpm)
    TEST_CMD="pnpm lint && pnpm test"
    DEV_CMD="pnpm dev"
    ;;
  yarn)
    TEST_CMD="yarn lint && yarn test"
    DEV_CMD="yarn dev"
    ;;
  npm)
    TEST_CMD="npm run lint && npm test"
    DEV_CMD="npm run dev"
    ;;
  python)
    TEST_CMD="pytest"
    DEV_CMD="python src/main.py"
    ;;
  rust)
    TEST_CMD="cargo clippy && cargo test"
    DEV_CMD="cargo run"
    ;;
  go)
    TEST_CMD="go vet ./... && go test ./..."
    DEV_CMD="go run ."
    ;;
  *)
    TEST_CMD="# TODO: Add your test command"
    DEV_CMD="# TODO: Add your dev command"
    ;;
esac

# Create AGENTS.md (root protocol)
cat > AGENTS.md << AGENTS_EOF
# AGENTS.md

> This file defines how AI agents operate in this codebase.
> Read this first. Follow it always.

## Quick Start

1. Read \`CONTINUITY.md\` (or create it if missing)
2. Determine if this is trivial (<15 min, no dependencies) or needs a ledger
3. Do the work
4. Update ledgers before finishing

---

## Project Overview

**What:** TODO: Describe your project in one line
**Stack:** TODO: e.g., React + Flask + PostgreSQL
**Test command:** \`$TEST_CMD\`
**Dev server:** \`$DEV_CMD\`

---

## Operating Principles

1. **Ledger-first:** Read CONTINUITY.md before working. Update it when state changes.
2. **Single source of truth:** Ledgers and repo are authoritative; chat may be incomplete.
3. **Small updates:** Bullets over paragraphs. Facts only.
4. **No guessing:** Mark uncertainty as UNCONFIRMED. Ask 1-3 targeted questions.
5. **Right-size ceremony:** Trivial tasks get one-liners; complex work gets ledgers.

---

## File Locations

| File | Purpose |
|------|---------|
| \`CONTINUITY.md\` | Master ledger — current project state |
| \`ledgers/\` | Epic, planning, and task ledgers |
| \`ledgers/archive/\` | Completed ledgers |
| \`scripts/ralph/\` | Autonomous execution loop |
| \`*/AGENTS.md\` | Subdirectory-specific conventions |

---

## Bootstrap (First Run)

If \`CONTINUITY.md\` doesn't exist, create it with:
- Goal: inferred from user request or UNCONFIRMED
- State: Now = current task, Next = TBD

---

## Interactive → Ralph Handoff

Tasks flow from interactive sessions to autonomous execution:

**Planning ledger is the single source of truth** — both modes use it.

### Task Status Flow

| Status | Meaning | Ralph Action |
|--------|---------|--------------|
| \`pending\` | Has unmet dependencies | Skip |
| \`ready\` | Unblocked, can be worked | **Pick this** |
| \`in-progress\` | Currently being worked | Skip |
| \`blocked\` | Needs decision/input | Skip |
| \`complete\` | Done | Skip |

### To Hand Off to Ralph

1. Set any \`in-progress\` tasks to \`ready\` (if stopping mid-work)
2. Ensure acceptance criteria are explicit
3. Commit current state
4. Run: \`./scripts/ralph/ralph.sh 25\`

### After Ralph Completes

1. Review commits and \`scripts/ralph/progress.txt\`
2. Resolve any \`blocked\` or \`failed\` tasks
3. Continue interactively or run Ralph again

---

## Ledger Protocol

### Start of Turn
1. Read \`CONTINUITY.md\`
2. Attach to existing ledger OR create new one OR use trivial protocol
3. Update stale state before new work

### During Work
Update ledgers when:
- Goals/constraints change
- Decisions made
- Milestones reached (Done/Now/Next)
- Tests run (record result)
- Blockers identified

### Trivial Tasks
Skip ledger creation when ALL true:
- < 15 minutes
- Single file change
- No cross-task dependencies

Log one-liner in CONTINUITY.md's "Trivial Log" section.

---

## Codebase Patterns

> Agents: Add patterns here when you discover reusable conventions.

(none yet — agents will populate this)

---

## Quality Bar

Before marking work complete:
- [ ] Tests pass (\`$TEST_CMD\`)
- [ ] Ledger state updated
- [ ] Patterns added to AGENTS.md if discovered
AGENTS_EOF

echo "Created AGENTS.md"

# Create CONTINUITY.md (master ledger)
cat > CONTINUITY.md << 'CONTINUITY_EOF'
# CONTINUITY.md

> Master ledger — canonical project state. Read this first every turn.

## Goal

TODO: Describe the project goal (or UNCONFIRMED if unknown)

## Constraints / Assumptions

- (fill in as discovered)

## Key Decisions

- Using AGENTS.md + Ralph workflow for autonomous task execution

## State

### Done
- Initial agent workflow setup

### Now
- Configure AGENTS.md with project-specific details

### Next
- Create first planning ledger when ready for tasks

## Task Map

```
CONTINUITY.md
  └─ ledgers/CONTINUITY_plan-example.md (template)
```

## Active Ledgers

| Ledger | Status | Owner | Blockers |
|--------|--------|-------|----------|
| CONTINUITY_plan-example.md | template | — | Rename for actual work |

## Trivial Log

- (none yet)

## Open Questions

- (none yet)

## Working Set

**Key files:**
- `CLAUDE.md` - Claude Code instructions (auto-loaded)
- `AGENTS.md` - Agent operating protocol
- `scripts/ralph/` - Autonomous execution scripts

**Useful commands:**
```bash
# TODO: Add your common commands here
```
CONTINUITY_EOF

echo "Created CONTINUITY.md"

# Create ralph.sh
cat > scripts/ralph/ralph.sh << 'RALPH_EOF'
#!/bin/bash
set -e

MAX_ITERATIONS=${1:-10}
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "Starting Ralph"
echo "   Max iterations: $MAX_ITERATIONS"
echo "   Project: $PROJECT_ROOT"
echo ""

cd "$PROJECT_ROOT"

for i in $(seq 1 $MAX_ITERATIONS); do
  echo "======================================="
  echo "   Iteration $i of $MAX_ITERATIONS"
  echo "======================================="

  # Pipe prompt to Claude Code
  # Alternative agents:
  #   amp --dangerously-allow-all
  #   aider --yes

  OUTPUT=$(cat "$SCRIPT_DIR/prompt.md" \
    | claude --dangerously-skip-permissions 2>&1 \
    | tee /dev/stderr) || true

  # Check for completion signal
  if echo "$OUTPUT" | grep -q "<ralph>COMPLETE</ralph>"; then
    echo ""
    echo "All tasks complete!"
    exit 0
  fi

  # Check for stop signal
  if echo "$OUTPUT" | grep -q "<ralph>STOP</ralph>"; then
    echo ""
    echo "Agent requested stop. Check progress.txt"
    exit 1
  fi

  sleep 2
done

echo ""
echo "Max iterations ($MAX_ITERATIONS) reached"
exit 1
RALPH_EOF

chmod +x scripts/ralph/ralph.sh
echo "Created scripts/ralph/ralph.sh"

# Create prompt.md
cat > scripts/ralph/prompt.md << 'PROMPT_EOF'
# Ralph Agent Instructions

You are running in **autonomous mode**. Complete one task per iteration, then exit.

## 1. Read State (MANDATORY)

You MUST read these files in order before doing anything else:

1. `AGENTS.md` → Project conventions and test commands
2. `CONTINUITY.md` → Current state, find active planning ledger
3. The active planning ledger from CONTINUITY.md → Task list
4. `scripts/ralph/progress.txt` → Learnings from previous iterations

## 2. Find Next Task

1. Open `CONTINUITY.md` → find the active planning ledger in "Active Ledgers" table
2. Open the planning ledger
3. Scan tasks for `**Status:** ready`
4. Pick the **first** `ready` task
5. If no `ready` tasks:
   - All `complete` → output `<ralph>COMPLETE</ralph>` and stop
   - All `pending`/`blocked` → output `<ralph>STOP</ralph>`

## 3. Implement

- Follow **Acceptance Criteria** exactly
- Check `*/AGENTS.md` files for patterns
- Make minimal, focused changes

## 4. Verify

Run the test command from AGENTS.md's "Project Overview" section.

## 5. On Success

1. Update planning ledger: `**Status:** ready` → `**Status:** complete`
2. Commit: `git commit -am "feat: TASK-XXX - [title]"`
3. Append to `scripts/ralph/progress.txt`
4. Check if completion unblocks other tasks → update `pending` to `ready`

## 6. On Failure

After 3 attempts:
1. Update planning ledger: status → `failed`
2. Update progress.txt with details
3. Output: `<ralph>STOP</ralph>`

## Stop Signals

- `<ralph>COMPLETE</ralph>` — All tasks done
- `<ralph>STOP</ralph>` — Cannot continue, needs human

## Rules

- ONE task per iteration
- Only pick `ready` tasks
- Update the planning ledger (source of truth)
- Always update progress.txt
- Commit after each success
PROMPT_EOF

echo "Created scripts/ralph/prompt.md"

# Create progress.txt
cat > scripts/ralph/progress.txt << PROGRESS_EOF
# Ralph Progress Log

**Started:** $(date +%Y-%m-%d)
**Planning Ledger:** (set when first planning ledger created)

---

## Codebase Patterns

> Discovered patterns persist here. Also update AGENTS.md.

- (none yet)

---

## Session Log

> Ralph appends after each iteration.

(awaiting first Ralph run)
PROGRESS_EOF

echo "Created scripts/ralph/progress.txt"

# Create example planning ledger
cat > ledgers/CONTINUITY_plan-example.md << 'PLAN_EOF'
# CONTINUITY_plan-example.md

> Example planning ledger. Rename or replace for your actual work.

**Parent:** CONTINUITY.md
**Root:** CONTINUITY.md
**Branch:** feature/example

---

## Objective

[Describe what this plan accomplishes]

---

## Tasks

### TASK-001: Example Task
- **Status:** ready
- **Owner:** —
- **Depends on:** —
- **Acceptance Criteria:**
  - [ ] First criterion
  - [ ] Second criterion
  - [ ] Tests pass
- **Notes:** This is an example. Replace with real tasks.

---

### TASK-002: Another Task
- **Status:** pending
- **Owner:** —
- **Depends on:** TASK-001
- **Acceptance Criteria:**
  - [ ] Criterion here
  - [ ] Tests pass
- **Notes:** Blocked until TASK-001 complete.

---

## Task Status Legend

| Status | Meaning | Ralph Action |
|--------|---------|--------------|
| `pending` | Has unmet dependencies | Skip |
| `ready` | Unblocked, can be worked | **Pick this** |
| `in-progress` | Currently being worked | Skip |
| `blocked` | Needs decision/input | Skip |
| `complete` | Done | Skip |

---

## Handoff Notes

**To hand off to Ralph:**
1. Set tasks to `ready` when criteria are clear
2. Run `./scripts/ralph/ralph.sh`
PLAN_EOF

echo "Created ledgers/CONTINUITY_plan-example.md"

# Update CLAUDE.md with agent protocol if it exists
AGENT_PROTOCOL='
## Agent Protocol (MANDATORY)

**CRITICAL: Before starting ANY work, you MUST:**

1. **Read `AGENTS.md`** - Contains operating principles, ledger protocol, and task flow rules
2. **Read `CONTINUITY.md`** - Master ledger with current project state and active tasks
3. **Check for active planning ledgers** in `ledgers/` directory

**This is not optional.** These files are the single source of truth for project state.

### Key Rules from AGENTS.md

- **Ledger-first:** Update CONTINUITY.md when state changes (goals, decisions, blockers)
- **Task statuses:** `pending` → `ready` → `in-progress` → `complete`
- **Quality bar:** Tests must pass before marking work complete
- **Trivial tasks** (<15 min, single file): Log one-liner in CONTINUITY.md Trivial Log

### Ralph Autonomous Mode

When running via `./scripts/ralph/ralph.sh`:
- Pick ONLY `ready` tasks from the active planning ledger
- Complete ONE task per iteration
- Update ledger status and commit after each task
- Output `<ralph>COMPLETE</ralph>` when all tasks done
- Output `<ralph>STOP</ralph>` when blocked
'

if [ -f "CLAUDE.md" ]; then
  # Check if agent protocol already exists
  if grep -q "Agent Protocol (MANDATORY)" CLAUDE.md; then
    echo "CLAUDE.md already has agent protocol, skipping"
  else
    echo "" >> CLAUDE.md
    echo "$AGENT_PROTOCOL" >> CLAUDE.md
    echo "Updated CLAUDE.md with agent protocol"
  fi
else
  # Create minimal CLAUDE.md with agent protocol
  cat > CLAUDE.md << CLAUDE_EOF
# CLAUDE.md

This file provides guidance to Claude Code when working with this repository.

## Project Overview

TODO: Describe your project here.
$AGENT_PROTOCOL
CLAUDE_EOF
  echo "Created CLAUDE.md with agent protocol"
fi

echo ""
echo "========================================"
echo "Setup complete!"
echo ""
echo "Files created/updated:"
echo "  - AGENTS.md (protocol)"
echo "  - CONTINUITY.md (master ledger)"
echo "  - CLAUDE.md (agent protocol added)"
echo "  - ledgers/CONTINUITY_plan-example.md"
echo "  - scripts/ralph/ralph.sh"
echo "  - scripts/ralph/prompt.md"
echo "  - scripts/ralph/progress.txt"
echo ""
echo "Detected stack: $STACK"
echo "Test command: $TEST_CMD"
echo ""
echo "Next steps:"
echo "  1. Edit AGENTS.md - fill in Project Overview (What, Stack)"
echo "  2. Edit CONTINUITY.md - set your project Goal"
echo "  3. Work with Claude - it will follow the protocol"
echo "  4. When ready for autonomous work:"
echo "     - Create a planning ledger with real tasks"
echo "     - Run: ./scripts/ralph/ralph.sh 25"
echo "========================================"
