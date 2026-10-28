from celery import shared_task
from django.utils import timezone

from apps.events.reminders import dispatch_due_reminders


@shared_task
def test_celery_task():
    print("✅ Celery task executed at:", timezone.now())
    return "CELERY_OK"


@shared_task
def dispatch_event_reminders():
    """
    Runs every minute (django-celery-beat periodic task "Dispatch Event
    Reminders Every Minute"). No automatic retries: a failed send stays
    unsent and is picked up by the next run, so nothing is sent twice.
    """
    return dispatch_due_reminders()
