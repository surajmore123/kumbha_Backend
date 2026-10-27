"""
Sending due event reminders (ScheduledNotification rows).

Called every minute by the Celery beat task `dispatch_event_reminders`, or
by `python manage.py run_reminder_dispatcher` where Celery/Redis isn't
running (local development).

Rules:
- A reminder is marked sent once FCM accepted the request (or the user has
  no registered device), so it is never sent twice.
- If Firebase is unavailable nothing is marked sent; the next run retries.
- Reminders for events that have already started, were unpublished or
  deleted, or whose subscription was turned off are skipped (soft-deleted)
  instead of arriving late.
- Rows are locked while being sent, so two workers can't send the same one.
"""

import logging

from django.db import transaction
from django.utils import timezone

from apps.events.models.schedule_notification import ScheduledNotification
from apps.events.utility import get_event_start_datetime
from utils.push_notifications import CHANNEL_EVENTS, send_to_user

logger = logging.getLogger(__name__)

_TITLES = {
    "en": "Event reminder",
    "hi": "कार्यक्रम स्मरण",
    "mr": "कार्यक्रम स्मरणपत्र",
}
_BODIES = {
    "en": "{event} starts in {when}.",
    "hi": "{event} {when} में शुरू होगा।",
    "mr": "{event} {when} सुरू होईल.",
}
_LOCATION = {"en": " Location: {place}", "hi": " स्थान: {place}", "mr": " ठिकाण: {place}"}


def _when(minutes: int, language: str) -> str:
    if minutes >= 1440 and minutes % 1440 == 0:
        n, unit = minutes // 1440, "day"
    elif minutes >= 60 and minutes % 60 == 0:
        n, unit = minutes // 60, "hour"
    else:
        n, unit = minutes, "minute"
    if language == "hi":
        return f"{n} " + {"day": "दिन", "hour": "घंटे", "minute": "मिनट"}[unit]
    if language == "mr":
        return f"{n} " + {
            "day": "दिवसात" if n == 1 else "दिवसांत",
            "hour": "तासात" if n == 1 else "तासांत",
            "minute": "मिनिटात" if n == 1 else "मिनिटांत",
        }[unit]
    return f"{n} {unit}{'' if n == 1 else 's'}"


def reminder_text(event, offset_minutes: int, language: str | None) -> tuple[str, str]:
    language = (language or "en").lower()[:2]
    if language not in _TITLES:
        language = "en"
    if offset_minutes <= 0:
        when = {"en": "now", "hi": "अभी", "mr": "आता"}[language]
        body = {
            "en": "{event} is starting now.",
            "hi": "{event} अभी शुरू हो रहा है।",
            "mr": "{event} आता सुरू होत आहे.",
        }[language].format(event=event.event_name)
    else:
        when = _when(offset_minutes, language)
        body = _BODIES[language].format(event=event.event_name, when=when)
    if event.location_name:
        body += _LOCATION[language].format(place=event.location_name)
    return _TITLES[language], body


def _skip_reason(reminder, now) -> str | None:
    subscription = reminder.subscription
    event = subscription.event
    if not subscription.is_active or subscription.del_flag:
        return "subscription_off"
    if event.status != "PUBLISHED" or event.del_flag:
        return "event_unavailable"
    if get_event_start_datetime(event) <= now:
        return "event_started"
    return None


def dispatch_due_reminders(now=None, limit: int = 100) -> dict:
    now = now or timezone.now()
    summary = {"sent": 0, "no_devices": 0, "skipped": 0, "deferred": 0}

    with transaction.atomic():
        due = list(
            ScheduledNotification.objects.select_for_update(skip_locked=True, of=("self",))
            .select_related("subscription__event", "subscription__user")
            .filter(scheduled_at__lte=now, is_sent=False, del_flag=0)
            .order_by("scheduled_at")[:limit]
        )
        for reminder in due:
            reason = _skip_reason(reminder, now)
            if reason:
                reminder.del_flag = 1
                reminder.save(update_fields=["del_flag"])
                summary["skipped"] += 1
                logger.info("Reminder %s skipped (%s).", reminder.pk, reason)
                continue

            user = reminder.subscription.user
            event = reminder.subscription.event
            title, body = reminder_text(event, reminder.offset_minutes, user.preferred_language)
            result = send_to_user(
                user,
                title,
                body,
                channel_id=CHANNEL_EVENTS,
                category="event_reminders",
                data={
                    "type": "event_reminder",
                    "event_id": event.event_id,
                    "route": "/shahiEvents",
                },
            )
            if result["status"] == "opted_out":
                # The user turned event reminders off in Settings.
                reminder.del_flag = 1
                reminder.save(update_fields=["del_flag"])
                summary["skipped"] += 1
                continue
            if result["status"] == "disabled":
                # Firebase unreachable: leave it unsent for the next run.
                summary["deferred"] += 1
                continue

            reminder.is_sent = True
            reminder.sent_at = timezone.now()
            reminder.save(update_fields=["is_sent", "sent_at"])
            summary["no_devices" if result["status"] == "no_devices" else "sent"] += 1

    if any(summary.values()):
        logger.info("Event reminders: %s", summary)
    return summary
