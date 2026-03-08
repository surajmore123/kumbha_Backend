#!/bin/sh

echo "Waiting for database..."

python manage.py migrate

echo "Collecting static files..."
python manage.py collectstatic --noinput

echo "Starting Django..."

exec "$@"