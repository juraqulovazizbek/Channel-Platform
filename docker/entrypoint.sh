#!/bin/bash
set -e

echo "Waiting for PostgreSQL..."
while ! nc -z "$DB_HOST" "$DB_PORT"; do
  sleep 0.5
done
echo "PostgreSQL is ready."

echo "Waiting for Redis..."
while ! nc -z "$REDIS_HOST" "$REDIS_PORT"; do
  sleep 0.5
done
echo "Redis is ready."

echo "Running migrations..."
python manage.py migrate --noinput

echo "Collecting static files..."
python manage.py collectstatic --noinput

echo "Registering Telegram webhook..."
python manage.py register_webhook || echo "Webhook registration skipped (may already be set)"

echo "Starting application..."
exec "$@"