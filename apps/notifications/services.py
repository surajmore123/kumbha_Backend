"""
Writing to the notification centre, and the outbox for critical messages.

`mirror` records what other modules already send. `queue` is for messages that
must be tracked and retried: the row exists before anything is sent, so a
failure is never silent.
"""

import logging
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from apps.notifications.models import Notification, NotificationDelivery
from utils.push_notifications import CHANNEL_EMERGENCY, send_localized

logger = logging.getLogger(__name__)

_RETRY_SECONDS = 30
# A row nobody tried, because the process stopped before sending.
_ORPHAN_AFTER = timedelta(minutes=1)


def _language(code):
    code = (code or "en").lower()[:2]
    return code if code in ("en", "hi", "mr") else "en"


def languages(user_ids):
    rows = get_user_model().objects.filter(pk__in=list(user_ids)).values_list("pk", "preferred_language")
    return {pk: _language(code) for pk, code in rows}


def _record(user_id, category, title, body, data, key):
    """The row, and whether it's new."""
    if key:
        try:
            with transaction.atomic():
                return Notification.objects.get_or_create(
                    user_id=user_id, dedupe_key=key,
                    defaults={"category": category, "title": title, "body": body, "data": data},
                )
        except IntegrityError:
            return Notification.objects.get(user_id=user_id, dedupe_key=key), False
    row = Notification.objects.create(user_id=user_id, category=category, title=title, body=body, data=data)
    return row, True


def mirror(users, category, build, data, key=""):
    """Puts a message another module is sending into each person's centre. It
    goes in even if they've muted the push: muting stops the buzz, not the record."""
    for user_id, language in languages(users).items():
        title, body = build(language)
        _record(user_id, category, title[:160], body[:500], data, f"{key}:{user_id}" if key else "")


def queue(user_id, category, *, title, body, push_title, push_body, data, key, critical=False, preference=None):
    """A tracked message. Inside a transaction, so sending waits for the commit."""
    row, created = _record(user_id, category, title[:160], body[:500], data, key)
    if created:
        NotificationDelivery.objects.create(
            notification=row, push_title=push_title[:160], push_body=push_body[:240], critical=critical,
        )
        transaction.on_commit(lambda: deliver([row.pk], preference))
    return row


def _attempt(delivery, preference=None):
    row = delivery.notification
    delivery.attempts += 1
    try:
        result = send_localized(
            None if delivery.critical else preference,
            lambda _language: (delivery.push_title, delivery.push_body),
            users=[row.user_id], data=row.data, channel_id=CHANNEL_EMERGENCY, private=True,
        )
        status = result["status"]
        accepted = status == "sent" and result["success"] > 0
    except Exception as exc:  # the row stays, to be retried
        logger.warning("Notification send failed (%s).", type(exc).__name__)
        status, accepted = "error", False
    if accepted:
        delivery.state = NotificationDelivery.State.SENT
        delivery.sent_at = timezone.now()
    elif status == "no_devices":
        delivery.state = NotificationDelivery.State.NO_DEVICE
    elif delivery.attempts >= NotificationDelivery.MAX_ATTEMPTS:
        delivery.state = NotificationDelivery.State.FAILED
    else:
        delivery.next_attempt_at = timezone.now() + timedelta(seconds=_RETRY_SECONDS * 2 ** delivery.attempts)
    delivery.save(update_fields=["state", "attempts", "next_attempt_at", "sent_at"])


def deliver(ids, preference=None):
    rows = NotificationDelivery.objects.filter(
        notification_id__in=ids, state=NotificationDelivery.State.PENDING,
    ).select_related("notification")
    for delivery in rows:
        _attempt(delivery, preference)


def retry_pending():
    """Run on a schedule by Celery beat. Returns how many were tried."""
    now = timezone.now()
    due = NotificationDelivery.objects.filter(
        Q(next_attempt_at__lte=now) | Q(next_attempt_at__isnull=True, created_at__lte=now - _ORPHAN_AFTER),
        state=NotificationDelivery.State.PENDING,
    ).select_related("notification")
    rows = list(due[:200])
    for delivery in rows:
        _attempt(delivery)
    return len(rows)
