#!/usr/bin/env bash
set -euo pipefail

BLOCK_FILE="/tmp/kvh-domain-block.caddy"
CADDY_FILE="/opt/homeserver/caddy/Caddyfile"

if [[ ! -f "$BLOCK_FILE" ]]; then
  echo "missing $BLOCK_FILE" >&2
  exit 1
fi

if grep -q "BEGIN_KVH_FORECAST" "$CADDY_FILE"; then
  awk '
    BEGIN {skip=0}
    /# BEGIN_KVH_FORECAST/ {skip=1; next}
    /# END_KVH_FORECAST/ {skip=0; next}
    skip==0 {print}
  ' "$CADDY_FILE" > /tmp/Caddyfile.clean
  cat /tmp/Caddyfile.clean "$BLOCK_FILE" > /tmp/Caddyfile.next
else
  cat "$CADDY_FILE" "$BLOCK_FILE" > /tmp/Caddyfile.next
fi

cp "$CADDY_FILE" /opt/homeserver/caddy/Caddyfile.bak
mv /tmp/Caddyfile.next "$CADDY_FILE"
rm -f /tmp/Caddyfile.clean "$BLOCK_FILE"
