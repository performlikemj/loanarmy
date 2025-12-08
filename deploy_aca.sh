#!/usr/bin/env bash
set -euo pipefail

# Go On Loan - ACA deployment script (local use)
# - Builds backend and frontend images and pushes to ACR
# - Grants AcrPull to app identities and updates Container Apps
# - Sets/updates ingress ports and prints FQDNs
#
# Prereqs: az CLI (containerapp, acr), jq, pnpm or npm
# Login: az login; az account set --subscription "$SUBSCRIPTION_ID"

# ---------------------------
# Config (override via env)
# ---------------------------
SUBSCRIPTION_ID="${SUBSCRIPTION_ID:-63ceeeac-fe3f-4bcb-b6d2-b7aa7fd6bf52}"
LOCATION="${LOCATION:-westus2}"
RG="${RG:-rg-loan-army-westus2}"
ENV_NAME="${ENV_NAME:-cae-loan-army}"
ACR_NAME="${ACR_NAME:-acrloanarmy}"
KV_NAME="${KV_NAME:-kv-loan-army}"
APP_BACKEND="${APP_BACKEND:-ca-loan-army-backend}"
APP_FRONTEND="${APP_FRONTEND:-ca-loan-army-frontend}"
APP_N8N="${APP_N8N:-ca-loan-army-n8n}"
TAG="${TAG:-prod}"
# Optional: weekly job name to keep in sync with backend image tag
JOB_WEEKLY_NAME="${JOB_WEEKLY_NAME:-job-weekly-newsletters}"
# Optional explicit API base for frontend build. If empty, derived from backend FQDN
VITE_API_BASE="${VITE_API_BASE:-}"

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$ROOT_DIR/loan-army-backend"
FRONTEND_DIR="$ROOT_DIR/loan-army-frontend"

log() { printf "\n==> %s\n" "$*"; }
warn() { printf "\n⚠️  %s\n" "$*"; }
err() { printf "\n❌ %s\n" "$*"; }
need() { command -v "$1" >/dev/null 2>&1 || { echo "Missing required command: $1"; exit 1; }; }

# ---------------------------
# Supabase Security Checks
# ---------------------------
# Set SKIP_SECURITY_CHECKS=1 to bypass (not recommended)
SKIP_SECURITY_CHECKS="${SKIP_SECURITY_CHECKS:-0}"
# Supabase connection (uses SUPA_ prefixed vars to avoid conflict with local DB)
SUPA_DB_HOST="${SUPA_DB_HOST:-db.snqwamzutbcbjgusubsa.supabase.co}"
SUPA_DB_NAME="${SUPA_DB_NAME:-postgres}"
SUPA_DB_USER="${SUPA_DB_USER:-postgres}"
SUPA_DB_PORT="${SUPA_DB_PORT:-5432}"
# SUPA_DB_PASSWORD should be set in environment

run_security_checks() {
  log "Running pre-deployment security checks..."
  
  if [[ -z "${SUPA_DB_PASSWORD:-}" ]]; then
    warn "SUPA_DB_PASSWORD not set - skipping database security checks"
    warn "Set SUPA_DB_PASSWORD to enable RLS verification"
    return 0
  fi
  
  if ! command -v psql >/dev/null 2>&1; then
    warn "psql not found - skipping database security checks"
    warn "Install postgresql-client to enable RLS verification"
    return 0
  fi
  
  # Query for tables in public schema without RLS enabled
  local rls_query="
    SELECT schemaname || '.' || tablename as table_name
    FROM pg_tables t
    LEFT JOIN pg_class c ON c.relname = t.tablename
    LEFT JOIN pg_namespace n ON n.oid = c.relnamespace AND n.nspname = t.schemaname
    WHERE t.schemaname = 'public'
      AND c.relrowsecurity = false
      AND t.tablename NOT LIKE 'pg_%'
      AND t.tablename NOT IN ('alembic_version', 'schema_migrations')
    ORDER BY t.tablename;
  "
  
  local tables_without_rls
  tables_without_rls=$(PGPASSWORD="$SUPA_DB_PASSWORD" psql \
    -h "$SUPA_DB_HOST" \
    -p "$SUPA_DB_PORT" \
    -U "$SUPA_DB_USER" \
    -d "$SUPA_DB_NAME" \
    -t -A \
    -c "$rls_query" 2>/dev/null) || {
    warn "Could not connect to Supabase database for security checks"
    return 0
  }
  
  if [[ -n "$tables_without_rls" ]]; then
    err "SECURITY CHECK FAILED: Tables without Row Level Security enabled:"
    echo ""
    echo "$tables_without_rls" | while read -r table; do
      echo "  ❌ $table"
    done
    echo ""
    err "All tables in public schema must have RLS enabled."
    err "Run: ALTER TABLE <table_name> ENABLE ROW LEVEL SECURITY;"
    err ""
    err "To bypass this check (NOT RECOMMENDED): SKIP_SECURITY_CHECKS=1 ./deploy_aca.sh"
    exit 1
  fi
  
  log "✅ Security checks passed - all tables have RLS enabled"
}

need az
need jq || true

# Run security checks before deployment (unless skipped)
if [[ "$SKIP_SECURITY_CHECKS" != "1" ]]; then
  run_security_checks
else
  warn "Security checks skipped (SKIP_SECURITY_CHECKS=1)"
fi

log "Setting subscription"
az account set --subscription "$SUBSCRIPTION_ID"

log "Upgrading containerapp extension if needed"
az extension add -n containerapp --upgrade -y >/dev/null 2>&1 || true

ACR_SERVER="$(az acr show -g "$RG" -n "$ACR_NAME" --query loginServer -o tsv)"

# ---------------------------
# Build backend
# ---------------------------
log "Building backend image in ACR ($TAG)"
az acr build -r "$ACR_NAME" -t "loanarmy/backend:$TAG" -f "$BACKEND_DIR/Dockerfile" "$BACKEND_DIR"

# ---------------------------
# Build frontend (Vite)
# ---------------------------
if [[ -z "${VITE_API_BASE}" ]]; then
  log "Deriving VITE_API_BASE from backend FQDN"
  BACKEND_FQDN="$(az containerapp show -g "$RG" -n "$APP_BACKEND" --query properties.configuration.ingress.fqdn -o tsv)"
  VITE_API_BASE="https://${BACKEND_FQDN}/api"
fi

log "Building frontend with VITE_API_BASE=${VITE_API_BASE}"
if command -v pnpm >/dev/null 2>&1; then
  ( cd "$FRONTEND_DIR" && pnpm install --frozen-lockfile && VITE_API_BASE="$VITE_API_BASE" pnpm run build )
else
  ( cd "$FRONTEND_DIR" && npm ci && VITE_API_BASE="$VITE_API_BASE" npm run build )
fi

# Ensure nginx.conf and Dockerfile.frontend exist (SPA fallback)
if [[ ! -f "$FRONTEND_DIR/nginx.conf" ]]; then
  cat > "$FRONTEND_DIR/nginx.conf" <<'NGINX'
server {
  listen 80;
  server_name _;
  root /usr/share/nginx/html;
  location / {
    try_files $uri $uri/ /index.html;
  }
}
NGINX
fi
if [[ ! -f "$FRONTEND_DIR/Dockerfile.frontend" ]]; then
  cat > "$FRONTEND_DIR/Dockerfile.frontend" <<'DF'
FROM nginx:1.25-alpine
COPY dist/ /usr/share/nginx/html/
COPY nginx.conf /etc/nginx/conf.d/default.conf
DF
fi

log "Building frontend image in ACR ($TAG)"
az acr build -r "$ACR_NAME" -t "loanarmy/frontend:$TAG" -f "$FRONTEND_DIR/Dockerfile.frontend" "$FRONTEND_DIR"

# ---------------------------
# Grant ACR pull to app identities (backend, frontend, n8n)
# ---------------------------
AcrScope="$(az acr show -g "$RG" -n "$ACR_NAME" --query id -o tsv)"
for APP in "$APP_BACKEND" "$APP_FRONTEND" "$APP_N8N"; do
  if az containerapp show -g "$RG" -n "$APP" >/dev/null 2>&1; then
    log "Assigning system identity to $APP"
    az containerapp identity assign -g "$RG" -n "$APP" --system-assigned >/dev/null
    PID="$(az containerapp show -g "$RG" -n "$APP" --query identity.principalId -o tsv)"
    log "Granting AcrPull to $APP ($PID)"
    az role assignment create --assignee "$PID" --role "AcrPull" --scope "$AcrScope" >/dev/null 2>&1 || true
    log "Setting container registry for $APP"
    az containerapp registry set -g "$RG" -n "$APP" --server "$ACR_SERVER" --identity system >/dev/null
  else
    log "Skipping ACR grant for $APP (app not found)"
  fi
done

# ---------------------------
# Update apps to ACR images and ingress
# ---------------------------
if az containerapp show -g "$RG" -n "$APP_BACKEND" >/dev/null 2>&1; then
  log "Updating backend image + ingress (force new revision)"
  az containerapp revision set-mode -g "$RG" -n "$APP_BACKEND" --mode single >/dev/null 2>&1 || true
  az containerapp update -g "$RG" -n "$APP_BACKEND" --image "$ACR_SERVER/loanarmy/backend:$TAG" --revision-suffix "r$RANDOM$RANDOM" >/dev/null
  az containerapp ingress enable -g "$RG" -n "$APP_BACKEND" --type external --target-port 5001 >/dev/null 2>&1 || true
fi

if az containerapp show -g "$RG" -n "$APP_FRONTEND" >/dev/null 2>&1; then
  log "Updating frontend image + ingress (force new revision)"
  az containerapp revision set-mode -g "$RG" -n "$APP_FRONTEND" --mode single >/dev/null 2>&1 || true
  az containerapp update -g "$RG" -n "$APP_FRONTEND" --image "$ACR_SERVER/loanarmy/frontend:$TAG" --revision-suffix "r$RANDOM$RANDOM" >/dev/null
  az containerapp ingress enable -g "$RG" -n "$APP_FRONTEND" --type external --target-port 80 >/dev/null 2>&1 || true
fi

# ---------------------------
# Sync scheduled job image tag (if job exists)
# ---------------------------
if az containerapp job show -g "$RG" -n "$JOB_WEEKLY_NAME" >/dev/null 2>&1; then
  log "Updating scheduled job '$JOB_WEEKLY_NAME' image to $ACR_SERVER/loanarmy/backend:$TAG"
  az containerapp job update -g "$RG" -n "$JOB_WEEKLY_NAME" \
    --image "$ACR_SERVER/loanarmy/backend:$TAG" >/dev/null
else
  log "Skipping job update (job '$JOB_WEEKLY_NAME' not found)"
fi

# ---------------------------
# Output endpoints
# ---------------------------
BE_FQDN="$(az containerapp show -g "$RG" -n "$APP_BACKEND" --query properties.configuration.ingress.fqdn -o tsv || true)"
FE_FQDN="$(az containerapp show -g "$RG" -n "$APP_FRONTEND" --query properties.configuration.ingress.fqdn -o tsv || true)"
N8N_FQDN="$(az containerapp show -g "$RG" -n "$APP_N8N" --query properties.configuration.ingress.fqdn -o tsv || true)"

log "Deployed images:"
echo "  Backend:  $ACR_SERVER/loanarmy/backend:$TAG"
echo "  Frontend: $ACR_SERVER/loanarmy/frontend:$TAG"

log "Endpoints:"
[[ -n "$FE_FQDN" ]] && echo "  Frontend: https://$FE_FQDN"
[[ -n "$BE_FQDN" ]] && echo "  Backend:  https://$BE_FQDN/api"
[[ -n "$N8N_FQDN" ]] && echo "  n8n:      https://$N8N_FQDN"

log "Done."
