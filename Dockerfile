# Production image for Render (free web service). See docs/hosting.md.
FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# mysqlclient is compiled from source on Linux and needs the MySQL client library.
# ca-certificates provides the CA bundle used for the TLS connection to the database.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential pkg-config default-libmysqlclient-dev ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# collectstatic only reads files; placeholder values satisfy the required settings.
RUN DJANGO_SECRET_KEY=build-only DB_NAME=build DB_USER=build DB_PASSWORD=build \
    python manage.py collectstatic --noinput \
    && chmod +x docker-entrypoint.sh \
    && useradd --create-home --uid 1000 app \
    && mkdir -p /app/media \
    && chown -R app:app /app/media

USER app

# Render passes the port in $PORT.
CMD ["./docker-entrypoint.sh"]
