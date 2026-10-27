"""
Firebase Cloud Messaging (FCM) sending.

Every push carries:
- a `notification` (title/body), so Android and iOS show it themselves
  when the app is in the background or closed;
- `data` (strings only), which the app uses to show the notification
  while it's open and to open the right screen when it's tapped;
- Android settings: high priority, the app's notification channel and its
  small status-bar icon.

Tokens FCM reports as dead (app uninstalled, token rotated) are marked
inactive. Tokens are sent in batches of 500, FCM's limit per request.

Every send names a `category` (see NotificationPreference.CATEGORIES);
users who turned that category off in Settings are left out.
"""

import logging

from firebase_admin import exceptions as firebase_exceptions
from firebase_admin import messaging

from apps.authentication.models import FCMDevice, NotificationPreference

logger = logging.getLogger(__name__)

# Must match the channels the app creates (NotificationService).
CHANNEL_ALERTS = "crowd_alerts"
CHANNEL_EVENTS = "event_reminders"

# Drawable in the Android app (white silhouette, required for the status bar).
ANDROID_ICON = "ic_stat_notification"
ANDROID_COLOR = "#E8761B"

_BATCH = 500


def _message(tokens, title, body, data, channel_id):
    return messaging.MulticastMessage(
        tokens=tokens,
        notification=messaging.Notification(title=title, body=body),
        data={str(k): str(v) for k, v in (data or {}).items() if v is not None},
        android=messaging.AndroidConfig(
            priority="high",
            notification=messaging.AndroidNotification(
                channel_id=channel_id,
                icon=ANDROID_ICON,
                color=ANDROID_COLOR,
                sound="default",
            ),
        ),
        apns=messaging.APNSConfig(
            headers={"apns-priority": "10"},
            payload=messaging.APNSPayload(aps=messaging.Aps(sound="default")),
        ),
    )


def _is_dead_token(exc) -> bool:
    if isinstance(exc, (messaging.UnregisteredError, messaging.SenderIdMismatchError)):
        return True
    return isinstance(exc, firebase_exceptions.InvalidArgumentError) and (
        "registration token" in str(exc).lower()
    )


def send_to_tokens(
    tokens,
    title,
    body,
    *,
    data=None,
    channel_id=CHANNEL_ALERTS,
    dry_run=False,
):
    """
    Send one notification to many devices.

    Returns {"status": "sent" | "no_devices" | "disabled", "success",
    "failure", "deactivated"}. "disabled" means Firebase isn't configured
    or couldn't be reached, so nothing was delivered.
    """
    tokens = [t for t in dict.fromkeys(tokens) if t]
    result = {"status": "sent", "success": 0, "failure": 0, "deactivated": 0}
    if not tokens:
        result["status"] = "no_devices"
        return result

    dead = []
    for start in range(0, len(tokens), _BATCH):
        batch = tokens[start:start + _BATCH]
        try:
            response = messaging.send_each_for_multicast(
                _message(batch, title, body, data, channel_id), dry_run=dry_run,
            )
        except ValueError:
            # firebase_admin.initialize_app() never ran (no credentials).
            logger.warning("Push not sent: Firebase is not configured.")
            result["status"] = "disabled"
            return result
        except firebase_exceptions.FirebaseError as exc:
            logger.error("Push batch failed (%s).", type(exc).__name__)
            result["status"] = "disabled"
            result["failure"] += len(batch)
            continue
        result["success"] += response.success_count
        result["failure"] += response.failure_count
        for token, item in zip(batch, response.responses):
            if not item.success and _is_dead_token(item.exception):
                dead.append(token)

    if dead and not dry_run:
        result["deactivated"] = FCMDevice.objects.filter(token__in=dead).update(is_active=False)
    if result["success"] and result["status"] == "disabled":
        result["status"] = "sent"
    logger.info(
        "Push '%s': %s sent, %s failed, %s tokens deactivated.",
        title, result["success"], result["failure"], result["deactivated"],
    )
    return result


def wants(user, category: str | None) -> bool:
    """True unless the user turned this category off."""
    if not category:
        return True
    if category not in NotificationPreference.CATEGORIES:
        raise ValueError(f"Unknown notification category: {category}")
    return not NotificationPreference.objects.filter(user=user, **{category: False}).exists()


def _active_devices(category: str | None):
    devices = FCMDevice.objects.filter(is_active=True)
    if category:
        if category not in NotificationPreference.CATEGORIES:
            raise ValueError(f"Unknown notification category: {category}")
        opted_out = NotificationPreference.objects.filter(**{category: False}).values("user_id")
        devices = devices.exclude(user_id__in=opted_out)
    return devices


def send_to_user(
    user, title, body, *, data=None, channel_id=CHANNEL_ALERTS, category=None, dry_run=False,
):
    if not wants(user, category):
        return {"status": "opted_out", "success": 0, "failure": 0, "deactivated": 0}
    tokens = FCMDevice.objects.filter(user=user, is_active=True).values_list("token", flat=True)
    return send_to_tokens(
        list(tokens), title, body, data=data, channel_id=channel_id, dry_run=dry_run,
    )


def send_test_push(user, title, body, data=None, channel_id=CHANNEL_ALERTS):
    """Kept for existing callers; sends to one user's active devices."""
    return send_to_user(user, title, body, data=data, channel_id=channel_id)


def send_push_to_all(title, body, data=None, channel_id=CHANNEL_ALERTS, category=None):
    """Sends to all active devices whose users want this category."""
    tokens = _active_devices(category).values_list("token", flat=True)
    return send_to_tokens(list(tokens), title, body, data=data, channel_id=channel_id)


def send_localized(
    category, text_for_language, *, data=None, channel_id=CHANNEL_ALERTS, users=None,
):
    """
    Broadcast in each user's preferred language.

    `text_for_language(code)` returns (title, body) for "en", "hi" or "mr";
    devices are grouped by their user's language. `users` (a queryset or
    list of ids) limits the audience, e.g. an event's subscribers.
    """
    devices = _active_devices(category)
    if users is not None:
        devices = devices.filter(user__in=users)
    by_language: dict[str, list[str]] = {}
    for token, language in devices.values_list("token", "user__preferred_language"):
        code = (language or "en").lower()[:2]
        by_language.setdefault(code if code in ("en", "hi", "mr") else "en", []).append(token)

    total = {"status": "no_devices", "success": 0, "failure": 0, "deactivated": 0}
    for code, tokens in by_language.items():
        title, body = text_for_language(code)
        result = send_to_tokens(tokens, title, body, data=data, channel_id=channel_id)
        for key in ("success", "failure", "deactivated"):
            total[key] += result[key]
        if result["status"] == "sent" or total["status"] == "no_devices":
            total["status"] = result["status"]
    return total
