#!/bin/bash
# Production entrypoint — runs before the CMD in Dockerfile.
# Waits for dependencies, runs migrations, registers webhook.

set -euo pipefail

# ── Helpers ──────────────────────────────────────────────────────────────────

log() {
    echo "[entrypoint] $(date -u '+%Y-%m-%dT%H:%M:%SZ') $*"
}

wait_for_service() {
    local host="$1"
    local port="$2"
    local name="$3"
    local max_attempts=30
    local attempt=0

    log "Waiting for $name at $host:$port..."
    until nc -z "$host" "$port"; do
        attempt=$((attempt + 1))
        if [ "$attempt" -ge "$max_attempts" ]; then
            log "ERROR: $name not available after $max_attempts attempts. Exiting."
            exit 1
        fi
        sleep 1
    done
    log "$name is available."
}

# ── Wait for dependencies ─────────────────────────────────────────────────────

wait_for_service "${DB_HOST:-postgres}" "${DB_PORT:-5432}" "PostgreSQL"
wait_for_service "${REDIS_HOST:-redis}" "${REDIS_PORT:-6379}" "Redis"

# ── Database migrations ───────────────────────────────────────────────────────
# Only run on the web container, not Celery workers.
# Detect by checking if CMD contains "gunicorn" or "celery".

if [[ "${1:-}" == *"gunicorn"* ]]; then
    log "Running database migrations..."
    python manage.py migrate --noinput

    log "Collecting static files..."
    python manage.py collectstatic --noinput --clear 2>/dev/null || true

    log "Registering Telegram webhook..."
    python manage.py register_webhook \
        --url "${TELEGRAM_WEBHOOK_URL:-}" \
        2>&1 || log "Webhook registration failed — check TELEGRAM_WEBHOOK_URL"
fi

# ── Celery beat: create periodic tasks in DB ──────────────────────────────────

if [[ "${1:-}" == *"beat"* ]]; then
    log "Ensuring Celery beat periodic tasks exist..."
    python manage.py migrate django_celery_beat --noinput 2>/dev/null || true
fi

log "Starting: $*"
exec "$@"