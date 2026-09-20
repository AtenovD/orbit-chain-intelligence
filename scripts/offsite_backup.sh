#!/bin/sh
# Copy the newest local Orbit backup to an off-server S3-compatible bucket with rclone.
#
# A backup that lives only on the VPS it protects is lost together with that VPS.
# Run this right after backup.sh (see DEPLOYMENT_MVP_RU.md).
#
# Required:  ORBIT_OFFSITE_REMOTE   an rclone remote path, e.g. "orbit-s3:my-bucket/orbit"
# Optional:  BACKUP_DIR             default /opt/orbit-backups
#
# It only ever COPIES. It never deletes anything remotely, so a bug or a wiped
# local directory cannot erase the off-site history; prune with a bucket
# lifecycle rule instead.
set -eu

backup_dir=${BACKUP_DIR:-/opt/orbit-backups}
remote=${ORBIT_OFFSITE_REMOTE:?Set ORBIT_OFFSITE_REMOTE, e.g. orbit-s3:my-bucket/orbit}

command -v rclone >/dev/null 2>&1 || { echo "rclone is not installed" >&2; exit 1; }

target=$(find "$backup_dir" -mindepth 1 -maxdepth 1 -type d -name '20*' | sort | tail -n 1)
test -n "$target" || { echo "No local backup found in $backup_dir" >&2; exit 1; }

# Never upload something that is already corrupt.
(cd "$target" && sha256sum -c SHA256SUMS >/dev/null)

name=$(basename "$target")
rclone copy "$target" "$remote/$name" --checksum --immutable
# Confirm the bytes on the far side match, not just that the copy returned.
rclone check "$target" "$remote/$name" --one-way >/dev/null
echo "Orbit backup uploaded and verified off-site: $remote/$name"
