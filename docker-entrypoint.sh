#!/bin/sh
# Start-up on Render: database migrations, optional first administrator and demo
# data, then the gunicorn web server. See docs/hosting.md.
# One worker process with threads: the login lockout and API limits live in the
# in-memory cache of that process (docs/bezpieczenstwo_aplikacji.md, section 11).
set -e

python manage.py migrate --noinput

# Creates the administrator once, when DJANGO_SUPERUSER_USERNAME and
# DJANGO_SUPERUSER_PASSWORD are set. Later starts skip an existing account.
if [ -n "$DJANGO_SUPERUSER_USERNAME" ] && [ -n "$DJANGO_SUPERUSER_PASSWORD" ]; then
    python manage.py createsuperuser --noinput \
        --username "$DJANGO_SUPERUSER_USERNAME" \
        --email "${DJANGO_SUPERUSER_EMAIL:-}" \
        || echo "Administrator not created (the account probably exists already)."
fi

# Demo records for one user (the command only adds what is missing).
if [ -n "$SEED_DEMO_DATA_FOR" ]; then
    python manage.py seed_demo_data --username "$SEED_DEMO_DATA_FOR"
fi

exec gunicorn config.wsgi:application \
    --bind "0.0.0.0:${PORT:-8000}" \
    --workers "${WEB_CONCURRENCY:-1}" \
    --threads 4 \
    --timeout 60 \
    --access-logfile -
