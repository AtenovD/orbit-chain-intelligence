#!/bin/sh
set -eu

if [ "${ORBIT_CONFIRM_RESTORE:-}" != "RESTORE" ]; then
  echo "Refusing destructive restore. Set ORBIT_CONFIRM_RESTORE=RESTORE." >&2
  exit 2
fi
if [ "$#" -ne 1 ]; then
  echo "Usage: ORBIT_CONFIRM_RESTORE=RESTORE $0 /opt/orbit-backups/<timestamp>" >&2
  exit 2
fi
project_dir=${ORBIT_PROJECT_DIR:-/root/orbemind}
target=$1
test -s "$target/database.dump"
test -s "$target/files.tar.gz"
cd "$target" && sha256sum -c SHA256SUMS
cd "$project_dir"
docker compose -f compose.yaml -f compose.production.yaml stop api
docker compose -f compose.yaml -f compose.production.yaml exec -T postgres \
  dropdb -U "${POSTGRES_USER:-orchestrator}" --if-exists "${POSTGRES_DB:-orchestrator}"
docker compose -f compose.yaml -f compose.production.yaml exec -T postgres \
  createdb -U "${POSTGRES_USER:-orchestrator}" "${POSTGRES_DB:-orchestrator}"
docker compose -f compose.yaml -f compose.production.yaml exec -T postgres \
  pg_restore -U "${POSTGRES_USER:-orchestrator}" -d "${POSTGRES_DB:-orchestrator}" --no-owner < "$target/database.dump"
docker compose -f compose.yaml -f compose.production.yaml run --rm -T api \
  sh -c 'rm -rf /app/data/files/* && tar -xzf - -C /app/data/files' < "$target/files.tar.gz"
docker compose -f compose.yaml -f compose.production.yaml up -d api
echo "Orbit restored from $target"
