from celery import shared_task
from django.utils import timezone
from celery import shared_task
from django.utils import timezone
from utils.push_notifications import send_test_push
from .models.schedule_notification import ScheduledNotification


@shared_task
def test_celery_task():
    print("✅ Celery task executed at:", timezone.now())
    return "CELERY_OK"





@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=30, retry_kwargs={"max_retries": 3})
def dispatch_event_reminders(self):
    now = timezone.now()

    reminders = (
        ScheduledNotification.objects
        .select_related("subscription__event", "subscription__user")
        .filter(
            scheduled_at__lte=now,
            is_sent=False,
            subscription__is_active=True
        )
        .order_by("scheduled_at")[:50]
    )

    for reminder in reminders:
        user = reminder.subscription.user
        event = reminder.subscription.event

        # TEMPORARY: replace with FCM in next step

        send_test_push(user=user,title="Event Reminder",body=f"{event.event_name} is coming soon")


        print(
            f"🔔 Reminder → User:{user.id} | "
            f"Event:{event.event_name} | "
            f"Time:{reminder.scheduled_at}"
        )

        reminder.is_sent = True
        reminder.sent_at = timezone.now()
        reminder.save()