#!/bin/sh
set -eu

url=${ORBIT_HEALTH_URL:-http://127.0.0.1:8000/api/v1/health}
state_dir=${ORBIT_STATE_DIR:-/var/lib/orbit-monitor}
mkdir -p "$state_dir"
stamp=$(date -u +%Y-%m-%dT%H:%M:%SZ)
if response=$(curl -fsS --max-time 15 "$url") && echo "$response" | grep -q '"status":"ok"'; then
  echo "$stamp healthy" > "$state_dir/last-success"
  rm -f "$state_dir/last-failure"
  exit 0
fi
echo "$stamp unhealthy url=$url" | tee "$state_dir/last-failure" >&2
exit 1
