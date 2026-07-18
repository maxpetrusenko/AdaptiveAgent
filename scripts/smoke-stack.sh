#!/usr/bin/env bash
set -euo pipefail

BACKEND_URL="${BACKEND_URL:-http://127.0.0.1:8000}"
FRONTEND_URL="${FRONTEND_URL:-http://127.0.0.1:3737}"
SMOKE_ATTEMPTS="${SMOKE_ATTEMPTS:-30}"
SMOKE_INTERVAL_SECONDS="${SMOKE_INTERVAL_SECONDS:-1}"

wait_for_endpoint() {
  local name="$1"
  local url="$2"
  local attempt

  for ((attempt = 1; attempt <= SMOKE_ATTEMPTS; attempt += 1)); do
    if curl --fail --silent --show-error --max-time 3 "$url" >/dev/null 2>&1; then
      printf 'ok: %s (%s)\n' "$name" "$url"
      return 0
    fi
    sleep "$SMOKE_INTERVAL_SECONDS"
  done

  printf 'error: %s did not become healthy after %s attempts (%s)\n' \
    "$name" "$SMOKE_ATTEMPTS" "$url" >&2
  return 1
}

probe_optional_health() {
  local name="$1"
  local url="$2"
  local status_code

  if ! status_code="$(
    curl --silent --show-error --max-time 3 \
      --output /dev/null --write-out '%{http_code}' "$url"
  )"; then
    printf 'error: %s could not be reached (%s)\n' "$name" "$url" >&2
    return 1
  fi
  case "$status_code" in
    200)
      printf 'ok: %s (%s)\n' "$name" "$url"
      ;;
    404)
      printf 'skip: %s is not mounted in this build (%s)\n' "$name" "$url"
      ;;
    *)
      printf 'error: %s returned HTTP %s (%s)\n' \
        "$name" "$status_code" "$url" >&2
      return 1
      ;;
  esac
}

verify_local_native_extension() {
  local backend_container

  if ! command -v docker >/dev/null 2>&1; then
    return 0
  fi
  backend_container="$(
    docker compose ps --quiet --status running backend 2>/dev/null || true
  )"
  if [[ -z "$backend_container" ]]; then
    return 0
  fi
  docker compose exec --no-TTY backend \
    python -c 'import adaptive_retrieval' >/dev/null
  printf 'ok: Rust ABI3 retrieval extension imports in backend container\n'
}

wait_for_endpoint "backend health" "${BACKEND_URL}/health"
wait_for_endpoint "frontend" "${FRONTEND_URL}/"
verify_local_native_extension
probe_optional_health "knowledge index health" \
  "${BACKEND_URL}/api/knowledge/index/health"
probe_optional_health "research health" "${BACKEND_URL}/api/research/health"

printf 'stack smoke passed\n'
