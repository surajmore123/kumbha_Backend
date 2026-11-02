from celery import shared_task

from apps.familylocation.services import sweep


@shared_task
def sweep_location_sessions():
    """Scheduled every minute by `manage.py setup_location_tasks`. Expiry is
    also enforced on every read and write, so this only tidies up and notifies."""
    return sweep()
