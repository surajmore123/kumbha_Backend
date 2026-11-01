from celery import shared_task

from apps.lostfound.notifications import retry_pending


@shared_task
def retry_case_notifications():
    """Scheduled every 2 minutes by `manage.py setup_lostfound_tasks`."""
    return retry_pending()
