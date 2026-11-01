"""
Tells people a case has moved, through the existing FCM sender.

Text is the same for every case and names nobody, because it shows on a lock
screen. The app opens the case, and the server checks access then.

Each notice is a row first, sent after commit. A failed send stays pending and is
retried by `retry_pending`, and the key means one event reaches a person once.
"""

import logging
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from apps.lostfound import policy
from apps.lostfound.models import CaseNotification
from utils.push_notifications import send_localized

logger = logging.getLogger(__name__)

_TITLE = {"en": "Kumbh Path case update", "hi": "कुंभ पथ मामला अपडेट", "mr": "कुंभ पथ प्रकरण अपडेट"}
_BODY = {
    "submitted": {
        "en": "Your report {ref} has been received.",
        "hi": "आपकी रिपोर्ट {ref} मिल गई है।",
        "mr": "तुमची नोंद {ref} मिळाली आहे.",
    },
    "reviewed": {
        "en": "Report {ref} is being reviewed.",
        "hi": "रिपोर्ट {ref} की समीक्षा हो रही है।",
        "mr": "नोंद {ref} तपासली जात आहे.",
    },
    "sighting": {
        "en": "There's an update on {ref}. Open the app to see it.",
        "hi": "{ref} पर अपडेट है। देखने के लिए ऐप खोलें।",
        "mr": "{ref} वर अपडेट आहे. पाहण्यासाठी अॅप उघडा.",
    },
    "match": {
        "en": "Staff are checking a possible lead on {ref}. Open the app.",
        "hi": "कर्मचारी {ref} पर एक संभावित सुराग जाँच रहे हैं। ऐप खोलें।",
        "mr": "कर्मचारी {ref} वरील संभाव्य धागा तपासत आहेत. अॅप उघडा.",
    },
    "confirmed": {
        "en": "Important update on {ref}. Open the app.",
        "hi": "{ref} पर महत्वपूर्ण अपडेट। ऐप खोलें।",
        "mr": "{ref} वर महत्त्वाचे अपडेट. अॅप उघडा.",
    },
    "reunited": {
        "en": "Report {ref} has been updated. Open the app.",
        "hi": "रिपोर्ट {ref} अपडेट हुई है। ऐप खोलें।",
        "mr": "नोंद {ref} अपडेट झाली आहे. अॅप उघडा.",
    },
    "meeting_point": {
        "en": "There's a meeting update on {ref}. Open the app.",
        "hi": "{ref} पर मिलने से जुड़ा अपडेट है। ऐप खोलें।",
        "mr": "{ref} वर भेटीबाबत अपडेट आहे. अॅप उघडा.",
    },
    "info_needed": {
        "en": "More information is needed for {ref}. Open the app.",
        "hi": "{ref} के लिए और जानकारी चाहिए। ऐप खोलें।",
        "mr": "{ref} साठी अधिक माहिती हवी आहे. अॅप उघडा.",
    },
    "staff_new": {
        "en": "New case {ref} needs review.",
        "hi": "नया मामला {ref} समीक्षा के लिए।",
        "mr": "नवीन प्रकरण {ref} तपासणीसाठी.",
    },
    "staff_update": {
        "en": "Case {ref} has new information.",
        "hi": "मामले {ref} में नई जानकारी है।",
        "mr": "प्रकरण {ref} मध्ये नवीन माहिती आहे.",
    },
}


def _queue(case, event, users, key, for_staff):
    rows = []
    for user_id in users:
        row, created = CaseNotification.objects.get_or_create(
            case=case, user_id=user_id, key=key, defaults={"event": event, "for_staff": for_staff},
        )
        if created:
            rows.append(row.pk)
    if rows:
        transaction.on_commit(lambda: deliver(rows))


def notify_family(case, event, key=None):
    _queue(case, event, policy.family_recipients(case), key or event, False)


def notify_staff(case, event, key=None):
    users = [u for u in policy.staff_recipients(case.zone_id) if u != case.reporter_id]
    _queue(case, event, users, key or event, True)


def _send(row):
    reference = row.case.reference

    def build(language):
        return _TITLE[language], _BODY[row.event][language].format(ref=reference)

    data = {
        "type": "lostfound_case",
        "route": "/lostFoundOpsCase" if row.for_staff else "/lostFoundCase",
        "case_id": str(row.case_id),
    }
    return send_localized(
        "safety_alerts", build, users=[row.user_id], data=data,
        inbox={"category": "lost_found", "key": f"lf:{row.pk}"},
    )


def _attempt(row):
    row.attempts += 1
    try:
        result = _send(row)
        status = result["status"]
        delivered = status == "sent" and result["success"] > 0
    except Exception as exc:  # the row stays, to be retried
        logger.warning("Case notification failed (%s).", type(exc).__name__)
        status, delivered = "error", False
    if delivered:
        row.state = CaseNotification.State.SENT
        row.sent_at = timezone.now()
    elif status == "no_devices":
        row.state = CaseNotification.State.NO_DEVICE  # no device, or turned off
    elif row.attempts >= CaseNotification.MAX_ATTEMPTS:
        row.state = CaseNotification.State.FAILED
    else:
        row.next_attempt_at = timezone.now() + timedelta(minutes=2 ** row.attempts)
    row.save(update_fields=["state", "attempts", "next_attempt_at", "sent_at"])


def deliver(ids):
    for row in CaseNotification.objects.filter(pk__in=ids, state="pending").select_related("case"):
        _attempt(row)


def retry_pending():
    """Run on a schedule by Celery beat. Returns how many were tried."""
    due = CaseNotification.objects.filter(state="pending", next_attempt_at__lte=timezone.now())
    rows = list(due.select_related("case")[:200])
    for row in rows:
        _attempt(row)
    return len(rows)
