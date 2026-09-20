#!/bin/sh
set -eu

project_dir=${ORBIT_PROJECT_DIR:-/root/orbemind}
backup_dir=${BACKUP_DIR:-/opt/orbit-backups}
retention_days=${BACKUP_RETENTION_DAYS:-14}
stamp=$(date -u +%Y%m%dT%H%M%SZ)
target="$backup_dir/$stamp"
lock="$backup_dir/.backup.lock"
mkdir -p "$backup_dir"
if ! mkdir "$lock" 2>/dev/null; then
  echo "Another Orbit backup is already running" >&2
  exit 1
fi
trap 'rm -rf "$lock"' EXIT INT TERM
mkdir -p "$target"
cd "$project_dir"

docker compose -f compose.yaml -f compose.production.yaml exec -T postgres pg_dump \
  -U "${POSTGRES_USER:-orchestrator}" \
  -d "${POSTGRES_DB:-orchestrator}" \
  -Fc > "$target/database.dump"
docker compose -f compose.yaml -f compose.production.yaml exec -T api \
  tar -czf - -C /app/data/files . > "$target/files.tar.gz"

test -s "$target/database.dump"
test -s "$target/files.tar.gz"
sha256sum "$target/database.dump" "$target/files.tar.gz" > "$target/SHA256SUMS"
cat > "$target/manifest.txt" <<EOF
created_at=$stamp
database=${POSTGRES_DB:-orchestrator}
retention_days=$retention_days
EOF
find "$backup_dir" -mindepth 1 -maxdepth 1 -type d -name '20*' -mtime "+$retention_days" -exec rm -rf {} \;
echo "Orbit backup created: $target"
