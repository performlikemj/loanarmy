#!/usr/bin/env bash
set -euo pipefail

# Scheduled Scaling Script for Go On Loan Backend
# 
# This script toggles minReplicas between 0 and 1 based on traffic patterns:
# - Peak hours (02:00-10:00 UTC): minReplicas=1 (always running, no cold starts)
# - Off-peak hours (10:00-02:00 UTC): minReplicas=0 (scale to zero when idle)
#
# Usage:
#   ./scheduled_scaling.sh peak      # Set minReplicas=1
#   ./scheduled_scaling.sh off-peak  # Set minReplicas=0
#
# To automate, set up two scheduled triggers:
#   1. At 02:00 UTC: ./scheduled_scaling.sh peak
#   2. At 10:00 UTC: ./scheduled_scaling.sh off-peak

# Configuration
SUBSCRIPTION_ID="${SUBSCRIPTION_ID:-63ceeeac-fe3f-4bcb-b6d2-b7aa7fd6bf52}"
RG="${RG:-rg-loan-army-westus2}"
APP_BACKEND="${APP_BACKEND:-ca-loan-army-backend}"

log() { printf "==> %s\n" "$*"; }
err() { printf "❌ %s\n" "$*" >&2; exit 1; }

# Validate input
MODE="${1:-}"
if [[ -z "$MODE" ]]; then
    echo "Usage: $0 <peak|off-peak>"
    echo ""
    echo "  peak      Set minReplicas=1 (UK evening / US afternoon traffic)"
    echo "  off-peak  Set minReplicas=0 (allow scale to zero)"
    exit 1
fi

# Set subscription
az account set --subscription "$SUBSCRIPTION_ID" 2>/dev/null || err "Failed to set subscription"

case "$MODE" in
    peak)
        log "Setting minReplicas=1 for peak hours..."
        az containerapp update \
            --name "$APP_BACKEND" \
            --resource-group "$RG" \
            --min-replicas 1 \
            --output none
        log "✅ Backend will maintain at least 1 replica (no cold starts)"
        ;;
    off-peak)
        log "Setting minReplicas=0 for off-peak hours..."
        az containerapp update \
            --name "$APP_BACKEND" \
            --resource-group "$RG" \
            --min-replicas 0 \
            --output none
        log "✅ Backend can now scale to zero when idle"
        ;;
    *)
        err "Unknown mode: $MODE (use 'peak' or 'off-peak')"
        ;;
esac

# Show current scaling config
log "Current scaling configuration:"
az containerapp show \
    --name "$APP_BACKEND" \
    --resource-group "$RG" \
    --query 'properties.template.scale.{minReplicas:minReplicas,maxReplicas:maxReplicas}' \
    --output table










