#!/bin/sh
set -eu

project_dir=${ORBIT_PROJECT_DIR:-/root/orbemind}
backup_dir=${BACKUP_DIR:-/opt/orbit-backups}
target=${1:-$(find "$backup_dir" -mindepth 1 -maxdepth 1 -type d -name '20*' | sort | tail -n 1)}
test -n "$target"
cd "$target"
sha256sum -c SHA256SUMS
tar -tzf files.tar.gz >/dev/null

cd "$project_dir"
verify_db="orbit_restore_verify_$(date -u +%s)"
cleanup() {
  docker compose -f compose.yaml -f compose.production.yaml exec -T postgres \
    dropdb -U "${POSTGRES_USER:-orchestrator}" --if-exists "$verify_db" >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM
docker compose -f compose.yaml -f compose.production.yaml exec -T postgres \
  createdb -U "${POSTGRES_USER:-orchestrator}" "$verify_db"
docker compose -f compose.yaml -f compose.production.yaml exec -T postgres \
  pg_restore -U "${POSTGRES_USER:-orchestrator}" -d "$verify_db" --no-owner < "$target/database.dump"
docker compose -f compose.yaml -f compose.production.yaml exec -T postgres \
  psql -U "${POSTGRES_USER:-orchestrator}" -d "$verify_db" -v ON_ERROR_STOP=1 \
  -c "SELECT count(*) AS users FROM users; SELECT count(*) AS workspaces FROM workspaces;" >/dev/null
echo "Orbit backup verified by real restore: $target"
