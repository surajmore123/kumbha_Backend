"""
Everything that changes an SOS. Views only check who's asking and what they sent.

The rules that matter are enforced here, so no route can get around them: only
responders reach the operational statuses, nothing resolves by itself, and every
step leaves a history row.
"""

from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.emergency import policy
from apps.emergency.models import (
    ACTIVE_STATUSES,
    EmergencyAudit,
    EmergencyRecipient,
    EmergencySOS,
    EmergencyStatusHistory,
    EmergencyUpdate,
    Status,
)
from apps.lostfound.policy import staff_recipients
from apps.notifications import services as inbox
from apps.notifications.models import Notification, NotificationDelivery
from apps.safety.policy import zone_ids
from apps.safety.zones import zone_for

Role = EmergencyStatusHistory.Role

TRANSITIONS = {
    Status.CREATED: {Status.SUBMITTED},
    Status.SUBMITTED: {Status.FAMILY_NOTIFIED, Status.ACKNOWLEDGED, Status.CANCELLED},
    Status.FAMILY_NOTIFIED: {Status.ACKNOWLEDGED, Status.CANCELLED},
    Status.ACKNOWLEDGED: {Status.ASSISTANCE_COORDINATED, Status.RESOLVED, Status.CANCELLED},
    Status.ASSISTANCE_COORDINATED: {Status.RESOLVED, Status.CANCELLED},
    Status.RESOLVED: {Status.CLOSED},
    Status.CANCELLED: {Status.CLOSED},
    Status.CLOSED: set(),
}
# Reachable only by an authorized operational user.
RESPONDER_ONLY = {Status.ACKNOWLEDGED, Status.ASSISTANCE_COORDINATED, Status.RESOLVED, Status.CLOSED}

_CATEGORY = {
    "medical": {"en": "Medical emergency", "hi": "चिकित्सा आपातकाल", "mr": "वैद्यकीय आणीबाणी"},
    "separated_vulnerable": {
        "en": "Child or elderly person separated", "hi": "बच्चा या बुज़ुर्ग बिछड़ गया", "mr": "मूल किंवा वृद्ध व्यक्ती हरवली",
    },
    "lost": {"en": "Lost or separated from family", "hi": "परिवार से बिछड़ गए", "mr": "कुटुंबापासून दुरावले"},
    "safety_threat": {"en": "Personal safety threat", "hi": "व्यक्तिगत सुरक्षा का खतरा", "mr": "वैयक्तिक सुरक्षेला धोका"},
    "accident": {"en": "Accident or injury", "hi": "दुर्घटना या चोट", "mr": "अपघात किंवा दुखापत"},
    "crowd": {"en": "Crowd-related emergency", "hi": "भीड़ से जुड़ा आपातकाल", "mr": "गर्दीशी संबंधित आणीबाणी"},
    "other": {"en": "Other emergency", "hi": "अन्य आपातकाल", "mr": "इतर आणीबाणी"},
}

# What can show on a lock screen: a reference, and no name, place or category.
_PUSH_TITLE = {"en": "Family emergency alert", "hi": "परिवार आपातकालीन सूचना", "mr": "कुटुंब आणीबाणी सूचना"}
_PUSH_BODY = {
    "en": "Reference {ref}. Open Kumbh Path to see it.",
    "hi": "संदर्भ {ref}। देखने के लिए Kumbh Path खोलें।",
    "mr": "संदर्भ {ref}. पाहण्यासाठी Kumbh Path उघडा.",
}

# Shown inside the app, behind the login.
_INBOX = {
    "submitted": {
        "en": "{name} sent an SOS", "hi": "{name} ने SOS भेजा", "mr": "{name} यांनी SOS पाठवला",
    },
    "staff_new": {
        "en": "New SOS from {name}", "hi": "{name} से नया SOS", "mr": "{name} कडून नवीन SOS",
    },
    "acknowledged": {
        "en": "A responder acknowledged this SOS", "hi": "एक सहायक ने इस SOS को स्वीकार किया",
        "mr": "एका मदतनीसाने हा SOS स्वीकारला",
    },
    "update": {
        "en": "New update on this SOS", "hi": "इस SOS पर नया अपडेट", "mr": "या SOS वर नवीन अपडेट",
    },
    "escalated": {
        "en": "This SOS was escalated to you", "hi": "यह SOS आपको आगे भेजा गया", "mr": "हा SOS तुमच्याकडे पाठवला",
    },
    "cancelled": {
        "en": "This SOS was cancelled", "hi": "यह SOS रद्द कर दिया गया", "mr": "हा SOS रद्द केला",
    },
    "resolved": {
        "en": "This SOS was marked resolved", "hi": "यह SOS हल के रूप में दर्ज हुआ", "mr": "हा SOS सुटल्याची नोंद झाली",
    },
    "closed": {
        "en": "This SOS was closed", "hi": "यह SOS बंद किया गया", "mr": "हा SOS बंद केला",
    },
}


class EmergencyError(Exception):
    def __init__(self, message, field="non_field_errors"):
        super().__init__(message)
        self.message = message
        self.field = field


class ActiveExists(Exception):
    def __init__(self, sos):
        super().__init__(sos.reference)
        self.sos = sos


def audit(sos, actor, action, **details):
    EmergencyAudit.objects.create(sos=sos, actor=actor, action=action, details=details)


def _display_name(sos):
    return (sos.user.full_Name or "").strip()


def _family_users(sos):
    return list(sos.recipients.filter(member__user__isnull=False).values_list("member__user_id", flat=True).distinct())


def _tell(sos, event, users, key=None, inbox_event=None):
    """One tracked message per person, sent after commit. Critical, so a muted
    category can't silence a family's emergency."""
    name = _display_name(sos)
    rows = {}
    for user_id, language in inbox.languages(set(users)).items():
        fallback = {"en": "A family member", "hi": "परिवार के एक सदस्य", "mr": "कुटुंबातील एक सदस्य"}[language]
        rows[user_id] = inbox.queue(
            user_id, Notification.Category.EMERGENCY,
            title=_INBOX[inbox_event or event][language].format(name=name or fallback),
            body=f"{_CATEGORY[sos.category][language]} · {sos.reference}",
            push_title=_PUSH_TITLE[language],
            push_body=_PUSH_BODY[language].format(ref=sos.reference),
            data={
                "type": "emergency_sos", "route": "/sosDetail", "sos_id": str(sos.pk),
                "reference": sos.reference, "category": sos.category,
            },
            key=f"sos:{sos.pk}:{key or event}:{user_id}",
            critical=True,
        )
    return rows


def _move(sos, to, actor, role, reason=""):
    if to not in TRANSITIONS.get(sos.status, set()):
        raise EmergencyError("This SOS can't move to that status now.", "status")
    previous = sos.status
    sos.status = to
    sos.save(update_fields=["status", "updated_at"])
    EmergencyStatusHistory.objects.create(
        sos=sos, from_status=previous, to_status=to, actor=actor, actor_role=role, reason=reason,
    )


def refresh_status(sos_id):
    """FAMILY_NOTIFIED only once the provider really accepted a message."""
    with transaction.atomic():
        sos = EmergencySOS.objects.select_for_update().filter(pk=sos_id, status=Status.SUBMITTED).first()
        if sos is None:
            return
        accepted = sos.recipients.filter(notification__delivery__state=NotificationDelivery.State.SENT).exists()
        if accepted:
            _move(sos, Status.FAMILY_NOTIFIED, None, Role.SYSTEM, "The notification provider accepted a message")


def create_sos(user, data):
    """Returns (sos, created). A retried request gets the same SOS back, and a
    second emergency while one is open returns that one to the app."""
    existing = EmergencySOS.objects.filter(user=user, client_id=data["client_id"]).first()
    if existing:
        return existing, False
    active = EmergencySOS.objects.filter(user=user, status__in=ACTIVE_STATUSES).first()
    if active:
        raise ActiveExists(active)
    try:
        with transaction.atomic():
            zone = zone_for(data.get("latitude"), data.get("longitude"))
            sos = EmergencySOS.objects.create(user=user, status=Status.CREATED, zone=zone, **data)
            EmergencyStatusHistory.objects.create(sos=sos, to_status=Status.CREATED, actor=user, actor_role=Role.PERSON)
            _move(sos, Status.SUBMITTED, user, Role.PERSON)
            audit(sos, user, "sos_created", category=sos.category, has_location=sos.latitude is not None)
            rows = {}
            for member in policy.family_members_to_tell(user):
                rows.setdefault(member.user_id, []).append(
                    EmergencyRecipient.objects.get_or_create(sos=sos, member=member, family=member.family)[0]
                )
            sent = _tell(sos, "submitted", rows)
            for user_id, notification in sent.items():
                for row in rows[user_id]:
                    row.notification = notification
                    row.save(update_fields=["notification"])
            coordinators = staff_recipients(sos.zone_id)
            _tell(sos, "staff", [u for u in coordinators if u != user.pk and u not in rows], inbox_event="staff_new")
            transaction.on_commit(lambda: refresh_status(sos.pk))
    except IntegrityError:
        again = EmergencySOS.objects.filter(user=user, client_id=data["client_id"]).first()
        if again:
            return again, False
        active = EmergencySOS.objects.filter(user=user, status__in=ACTIVE_STATUSES).first()
        if active:
            raise ActiveExists(active) from None
        raise
    return sos, True


def _active_only(sos):
    if not sos.is_active:
        raise EmergencyError("This SOS is no longer active.")


def _everyone(sos, owner=True):
    users = _family_users(sos)
    return [*users, sos.user_id] if owner else users


@transaction.atomic
def cancel(sos, by, reason):
    sos = EmergencySOS.objects.select_for_update().get(pk=sos.pk)
    _active_only(sos)
    reason = (reason or "").strip()
    if len(reason) < 3:
        raise EmergencyError("Say why you're cancelling.", "reason")
    sos.cancel_reason = reason[:300]
    _move(sos, Status.CANCELLED, by, Role.PERSON, sos.cancel_reason)
    sos.save(update_fields=["cancel_reason", "updated_at"])
    audit(sos, by, "sos_cancelled")
    _tell(sos, "cancelled", [*_family_users(sos), *([sos.assigned_to_id] if sos.assigned_to_id else [])])
    return sos


@transaction.atomic
def add_info(sos, by, body):
    _active_only(sos)
    update = EmergencyUpdate.objects.create(sos=sos, author=by, kind=EmergencyUpdate.Kind.PERSON, body=body)
    audit(sos, by, "info_added")
    _tell(sos, "update", _family_users(sos), key=f"update:{update.pk}")
    return sos


@transaction.atomic
def update_location(sos, by, data):
    """Only ever from the person pressing a button. There's no tracking here."""
    _active_only(sos)
    for field in ("latitude", "longitude", "accuracy_m", "location_at", "location_text"):
        if field in data:
            setattr(sos, field, data[field])
    sos.zone = zone_for(sos.latitude, sos.longitude) or sos.zone
    sos.save()
    update = EmergencyUpdate.objects.create(sos=sos, author=by, kind=EmergencyUpdate.Kind.LOCATION)
    audit(sos, by, "location_updated", has_coordinates="latitude" in data)
    _tell(sos, "update", _family_users(sos), key=f"update:{update.pk}")
    return sos


def family_acknowledge(sos, recipient):
    if recipient.acknowledged_at is None:
        recipient.acknowledged_at = timezone.now()
        recipient.save(update_fields=["acknowledged_at"])
        audit(sos, recipient.member.user, "family_acknowledged")
    return sos


@transaction.atomic
def acknowledge(sos, by):
    sos = EmergencySOS.objects.select_for_update().get(pk=sos.pk)
    _move(sos, Status.ACKNOWLEDGED, by, Role.RESPONDER)
    audit(sos, by, "responder_acknowledged")
    _tell(sos, "acknowledged", _everyone(sos))
    return sos


@transaction.atomic
def coordinate(sos, by, remarks):
    sos = EmergencySOS.objects.select_for_update().get(pk=sos.pk)
    _move(sos, Status.ASSISTANCE_COORDINATED, by, Role.RESPONDER, remarks)
    update = EmergencyUpdate.objects.create(sos=sos, author=by, kind=EmergencyUpdate.Kind.RESPONDER, body=remarks)
    audit(sos, by, "assistance_coordinated")
    _tell(sos, "update", _everyone(sos), key=f"update:{update.pk}")
    return sos


@transaction.atomic
def responder_update(sos, by, body, internal=False):
    _active_only(sos)
    kind = EmergencyUpdate.Kind.INTERNAL if internal else EmergencyUpdate.Kind.RESPONDER
    update = EmergencyUpdate.objects.create(sos=sos, author=by, kind=kind, body=body)
    audit(sos, by, "responder_update", kind=kind)
    if not internal:
        _tell(sos, "update", _everyone(sos), key=f"update:{update.pk}")
    return sos


@transaction.atomic
def assign(sos, by, assignee):
    if not policy.is_assignable(assignee):
        raise EmergencyError("Choose an authorized responder.", "assignee")
    if sos.zone_id and not assignee.is_superuser and sos.zone_id not in zone_ids(assignee):
        raise EmergencyError("This responder doesn't cover this zone.", "assignee")
    sos.assigned_to = assignee
    sos.save(update_fields=["assigned_to", "updated_at"])
    audit(sos, by, "assigned")
    return sos


@transaction.atomic
def escalate(sos, by, reason):
    """Asks coordinators to look. It changes no status: a responder still has
    to act, and an escalation dispatches nobody."""
    _active_only(sos)
    update = EmergencyUpdate.objects.create(
        sos=sos, author=by, kind=EmergencyUpdate.Kind.INTERNAL, body=f"Escalated: {reason}",
    )
    audit(sos, by, "escalated")
    _tell(sos, "escalated", [u for u in staff_recipients(sos.zone_id) if u != by.pk], key=f"escalated:{update.pk}")
    return sos


@transaction.atomic
def resolve(sos, by, note):
    sos = EmergencySOS.objects.select_for_update().get(pk=sos.pk)
    sos.resolution_note = note[:500]
    sos.resolved_at = timezone.now()
    _move(sos, Status.RESOLVED, by, Role.RESPONDER, sos.resolution_note)
    sos.save(update_fields=["resolution_note", "resolved_at", "updated_at"])
    audit(sos, by, "resolved")
    _tell(sos, "resolved", _everyone(sos))
    return sos


@transaction.atomic
def close(sos, by, remarks):
    sos = EmergencySOS.objects.select_for_update().get(pk=sos.pk)
    _move(sos, Status.CLOSED, by, Role.RESPONDER, remarks)
    audit(sos, by, "closed")
    _tell(sos, "closed", _everyone(sos))
    return sos


def sweep():
    """Run on a schedule by Celery beat: retries sends, and removes coordinates
    from finished emergencies once they're no longer needed. It never changes
    the status of an open SOS, except to record that a retry got through."""
    tried = inbox.retry_pending()
    for sos_id in EmergencySOS.objects.filter(status=Status.SUBMITTED).values_list("pk", flat=True)[:500]:
        refresh_status(sos_id)
    keep_until = timezone.now() - timedelta(days=settings.EMERGENCY_LOCATION_RETENTION_DAYS)
    EmergencySOS.objects.filter(
        status__in=[Status.RESOLVED, Status.CANCELLED, Status.CLOSED], updated_at__lte=keep_until,
        latitude__isnull=False,
    ).update(latitude=None, longitude=None, accuracy_m=None)
    return tried
