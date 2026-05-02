#!/usr/bin/env bash
# KVH Forecast daily automation.
#
# Runs every night via cron. Steps (each isolated, failures are logged
# but don't abort subsequent steps):
#   1. Login → bearer token
#   2. Weather ingest — also triggers water-level scraper (if enabled)
#      and push dispatch internally via the /v1/admin/ingest/weather hook.
#   3. Weather DQ (data-quality)
#   4. ML retrain (succeeds only when enough catch data accrues)
#
# Logs to ~/fishing-forecast/logs/kvh-daily-YYYY-MM-DD.log with one line
# per step (timestamp + result). Rotation is daily filename; clean up
# manually or via logrotate if needed.
#
# Env overrides (defaults shown):
#   BASE_URL  http://127.0.0.1:8000
#   USERNAME  demo
#   PASSWORD  demo123
#   LOG_DIR   $HOME/fishing-forecast/logs
set -uo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:8000}"
USERNAME="${USERNAME:-demo}"
PASSWORD="${PASSWORD:-demo123}"
LOG_DIR="${LOG_DIR:-$HOME/fishing-forecast/logs}"
LOG_RETENTION_DAYS="${LOG_RETENTION_DAYS:-14}"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/kvh-daily-$(date +%Y-%m-%d).log"

# Prune old daily logs (older than LOG_RETENTION_DAYS). Quietly skip if no
# matches. -mtime +N matches files modified more than N*24h ago.
find "$LOG_DIR" -maxdepth 1 -name 'kvh-daily-*.log' -type f \
  -mtime "+${LOG_RETENTION_DAYS}" -delete 2>/dev/null || true

ts() { date '+%Y-%m-%dT%H:%M:%S%z'; }
log() { printf '[%s] %s\n' "$(ts)" "$*" >> "$LOG"; }

log "=== daily run started ==="

# 1. Login. Use --data-binary to keep JSON body byte-exact.
LOGIN_BODY=$(printf '{"username":"%s","password":"%s"}' "$USERNAME" "$PASSWORD")
TOKEN_JSON=$(curl -fsS -X POST "$BASE_URL/v1/auth/login" \
  -H 'Content-Type: application/json' \
  --data-binary "$LOGIN_BODY" 2>>"$LOG" || true)
TOKEN=$(printf '%s' "$TOKEN_JSON" \
  | python3 -c 'import sys,json
try:
    print(json.load(sys.stdin).get("access_token",""))
except Exception:
    pass' 2>>"$LOG")

if [ -z "${TOKEN:-}" ]; then
  log "FATAL: login failed (response: ${TOKEN_JSON:0:200})"
  exit 1
fi
log "login ok (token len=${#TOKEN})"

api_post() {
  local path="$1"
  curl -fsS -X POST "$BASE_URL$path" \
    -H "Authorization: Bearer $TOKEN" \
    -H 'Content-Type: application/json' 2>>"$LOG" || echo '{"error":"curl_failed"}'
}

api_get() {
  local path="$1"
  curl -fsS "$BASE_URL$path" \
    -H "Authorization: Bearer $TOKEN" 2>>"$LOG" || echo '{"error":"curl_failed"}'
}

# 2. Weather ingest (also runs water-level scrape + push dispatch via the
# admin/ingest/weather hook chain).
INGEST_RESULT=$(api_post /v1/admin/ingest/weather)
log "ingest: $INGEST_RESULT"

# 3. DQ.
DQ_RESULT=$(api_get /v1/admin/dq/weather)
log "dq: $DQ_RESULT"

# 4. ML retrain (best-effort).
ML_RESULT=$(api_post /v1/admin/ml/retrain)
log "ml_retrain: $ML_RESULT"

log "=== daily run completed ==="
