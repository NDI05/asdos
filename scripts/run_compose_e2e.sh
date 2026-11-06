#!/usr/bin/env bash
set -euo pipefail
umask 077

project="asdos-e2e-$(date -u +%Y%m%d%H%M%S)-$$"
scratch_dir="$(mktemp -d /tmp/asdos-e2e.XXXXXX)"
chmod 700 "$scratch_dir"
env_file="$scratch_dir/compose.env"
db_password="$(openssl rand -hex 32)"
session_secret="$(openssl rand -hex 48)"
cat > "$env_file" <<EOF
ASDOS_DB_PASSWORD=$db_password
ASDOS_SESSION_SECRET=$session_secret
ASDOS_API_PUBLISH=127.0.0.1:0:8000
ASDOS_EXPORT_RETENTION_DAYS=0
EOF
unset db_password session_secret

root="$(cd "$(dirname "$0")/.." && pwd)"
compose=(docker compose --project-name "$project" --env-file "$env_file" -f "$root/deploy/compose.yaml")

cleanup() {
  "${compose[@]}" down -v --remove-orphans >/dev/null 2>&1 || true
  rm -rf -- "$scratch_dir"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

"${compose[@]}" --profile test run --build --rm e2e
