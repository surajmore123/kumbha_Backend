"""
Push notifications triggered by changes to events (admin or API saves).

- A visible event (published, verified, shown in the app) appears for the
  first time  → "new event" to everyone who wants `new_events`.
- A visible upcoming event changes date, time or place → its subscribers
  get an update (`event_updates`) and their pending reminders move to the
  new time, so they don't fire at the old one.
- A visible upcoming event is withdrawn (unpublished, hidden, deleted) →
  subscribers are told and its pending reminders are cancelled.

Everything runs after the database commit and never raises: a push problem
must not block saving an event.
"""

import logging

from django.db import transaction
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone

from apps.events.models.EventModel import Event
from apps.events.models.event_subscription import EventSubscription
from apps.events.models.schedule_notification import ScheduledNotification
from apps.events.utility import DEFAULT_REMINDER_OFFSETS, get_event_start_datetime
from utils.push_notifications import CHANNEL_EVENTS, send_localized

logger = logging.getLogger(__name__)

_WATCHED = ("event_date", "start_time", "location_name")

_TEXT = {
    "new": {
        "en": ("New event: {name}", "{when}{place}. Tap to see the schedule."),
        "hi": ("नया कार्यक्रम: {name}", "{when}{place}। कार्यक्रम देखने के लिए टैप करें।"),
        "mr": ("नवीन कार्यक्रम: {name}", "{when}{place}. वेळापत्रक पाहण्यासाठी टॅप करा."),
    },
    "updated": {
        "en": ("Event updated: {name}", "Now {when}{place}."),
        "hi": ("कार्यक्रम में बदलाव: {name}", "अब {when}{place}।"),
        "mr": ("कार्यक्रमात बदल: {name}", "आता {when}{place}."),
    },
    "withdrawn": {
        "en": ("Event withdrawn: {name}", "This event is no longer on the KumbhaPath schedule. Please check official announcements."),
        "hi": ("कार्यक्रम हटाया गया: {name}", "यह कार्यक्रम अब KumbhaPath सूची में नहीं है। कृपया आधिकारिक घोषणाएँ देखें।"),
        "mr": ("कार्यक्रम काढला: {name}", "हा कार्यक्रम आता KumbhaPath यादीत नाही. कृपया अधिकृत घोषणा पहा."),
    },
}


def is_visible(event) -> bool:
    return (
        event.status == "PUBLISHED"
        and event.is_verified
        and event.show_in_app
        and not event.del_flag
    )


def _is_upcoming(event) -> bool:
    return get_event_start_datetime(event) > timezone.now()


def _when(event) -> str:
    text = event.event_date.strftime("%d %b %Y")
    if event.start_time:
        text += ", " + event.start_time.strftime("%I:%M %p").lstrip("0")
    return text


def _texts(kind, event):
    place = f" · {event.location_name}" if event.location_name else ""

    def build(language):
        title, body = _TEXT[kind][language]
        return (
            title.format(name=event.event_name),
            body.format(when=_when(event), place=place),
        )

    return build


def reschedule_reminders(event) -> int:
    """Rebuild unsent reminders of active subscriptions from the event time."""
    start = get_event_start_datetime(event)
    now = timezone.now()
    created = 0
    for subscription in EventSubscription.objects.filter(event=event, is_active=True, del_flag=0):
        ScheduledNotification.objects.filter(subscription=subscription, is_sent=False).delete()
        for offset in subscription.reminder_offsets or DEFAULT_REMINDER_OFFSETS:
            scheduled_at = start - timezone.timedelta(minutes=offset)
            if scheduled_at > now:
                ScheduledNotification.objects.create(
                    subscription=subscription, scheduled_at=scheduled_at, offset_minutes=offset,
                )
                created += 1
    return created


def _subscribers(event):
    return EventSubscription.objects.filter(
        event=event, is_active=True, del_flag=0,
    ).values("user_id")


def handle_event_saved(event, previous: dict | None) -> str | None:
    """Decide and send. Returns what was sent ("new", "updated", "withdrawn")."""
    visible_now = is_visible(event)
    visible_before = previous is not None and previous["visible"]
    data = {"event_id": event.event_id, "route": "/shahiEvents"}

    if visible_now and not visible_before:
        if not _is_upcoming(event):
            return None
        send_localized(
            "new_events", _texts("new", event),
            data={**data, "type": "new_event"}, channel_id=CHANNEL_EVENTS,
        )
        return "new"

    if visible_now and visible_before:
        changed = any(previous[field] != getattr(event, field) for field in _WATCHED)
        if not changed or not _is_upcoming(event):
            return None
        reschedule_reminders(event)
        send_localized(
            "event_updates", _texts("updated", event),
            data={**data, "type": "event_update"}, channel_id=CHANNEL_EVENTS,
            users=_subscribers(event),
        )
        return "updated"

    if visible_before and not visible_now:
        ScheduledNotification.objects.filter(
            subscription__event=event, is_sent=False,
        ).update(del_flag=1)
        if not _is_upcoming(event):
            return None
        send_localized(
            "event_updates", _texts("withdrawn", event),
            data={**data, "type": "event_update"}, channel_id=CHANNEL_EVENTS,
            users=_subscribers(event),
        )
        return "withdrawn"
    return None


@receiver(pre_save, sender=Event)
def _remember_previous(sender, instance, **kwargs):
    instance._notification_previous = None
    if instance._state.adding or not instance.pk:
        return
    old = Event.objects.filter(pk=instance.pk).first()
    if old is not None:
        instance._notification_previous = {
            "visible": is_visible(old),
            **{field: getattr(old, field) for field in _WATCHED},
        }


@receiver(post_save, sender=Event)
def _event_saved(sender, instance, raw=False, **kwargs):
    if raw:  # loaddata
        return
    previous = getattr(instance, "_notification_previous", None)

    def run():
        try:
            handle_event_saved(instance, previous)
        except Exception:  # noqa: BLE001 - never break an event save
            logger.exception("Event notification failed for %s.", instance.pk)

    transaction.on_commit(run)
