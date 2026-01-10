#!/bin/bash
set -e

MAX_ITERATIONS=${1:-10}
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "🚀 Starting Ralph"
echo "   Max iterations: $MAX_ITERATIONS"
echo "   Project: $PROJECT_ROOT"
echo ""

cd "$PROJECT_ROOT"

for i in $(seq 1 $MAX_ITERATIONS); do
  echo "═══════════════════════════════════════"
  echo "   Iteration $i of $MAX_ITERATIONS"
  echo "═══════════════════════════════════════"
  
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
    echo "✅ All tasks complete!"
    exit 0
  fi
  
  # Check for stop signal
  if echo "$OUTPUT" | grep -q "<ralph>STOP</ralph>"; then
    echo ""
    echo "🛑 Agent requested stop. Check progress.txt"
    exit 1
  fi
  
  sleep 2
done

echo ""
echo "⚠️  Max iterations ($MAX_ITERATIONS) reached"
exit 1
