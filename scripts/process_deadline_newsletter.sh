#!/usr/bin/env bash
set -euo pipefail

# Run the weekly deadline newsletter processing job.
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"

# Load environment variables (includes ADMIN_API_KEY)
set -a
# shellcheck disable=SC1091
source "${PROJECT_ROOT}/.env"
set +a

API_URL="https://your-api.com/api/newsletters/deadline/process"
: "${ADMIN_API_KEY:?ADMIN_API_KEY is not set in .env}"

curl --fail-with-body --show-error --silent \
  -X POST "${API_URL}" \
  -H "X-API-Key: ${ADMIN_API_KEY}" \
  --max-time 30

echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] deadline newsletter job completed" >> "${PROJECT_ROOT}/logs/cron_deadline_newsletter.log"
