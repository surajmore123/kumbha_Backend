#!/bin/sh

echo "Waiting for database..."

python manage.py migrate

echo "Registering background tasks..."
python manage.py setup_location_tasks
python manage.py setup_lostfound_tasks
python manage.py setup_emergency_tasks

echo "Collecting static files..."
python manage.py collectstatic --noinput

echo "Starting Django..."

exec "$@"