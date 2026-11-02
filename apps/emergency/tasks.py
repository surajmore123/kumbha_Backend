from celery import shared_task

from apps.emergency.services import sweep


@shared_task
def sweep_emergencies():
    """Scheduled every minute by `manage.py setup_emergency_tasks`."""
    return sweep()
