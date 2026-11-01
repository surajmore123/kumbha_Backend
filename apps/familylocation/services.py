"""
Everything that changes a session. `settle` runs before any read or write, so an
expired session can never be served, even if the scheduled sweep hasn't run.
"""

import logging
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from apps.family.views import audit
from apps.familylocation.models import LocationRecipient, LocationSession, MemberLocation
from utils.push_notifications import send_localized

logger = logging.getLogger(__name__)

STANDARD_MINUTES = (30, 60, 180, 360)

_TITLE = {"en": "Family location", "hi": "परिवार स्थान", "mr": "कुटुंब स्थान"}
_BODY = {
    "started": {
        "en": "A family member started sharing their location with you.",
        "hi": "परिवार के एक सदस्य ने आपके साथ अपना स्थान साझा करना शुरू किया।",
        "mr": "कुटुंबातील एका सदस्याने तुमच्यासोबत स्थान शेअर करणे सुरू केले.",
    },
    "stopped": {
        "en": "A family member stopped sharing their location with you.",
        "hi": "परिवार के एक सदस्य ने आपके साथ स्थान साझा करना बंद किया।",
        "mr": "कुटुंबातील एका सदस्याने तुमच्यासोबत स्थान शेअर करणे बंद केले.",
    },
    "expired": {
        "en": "A family member's location sharing has ended.",
        "hi": "परिवार के एक सदस्य का स्थान साझा करना समाप्त हो गया।",
        "mr": "कुटुंबातील एका सदस्याचे स्थान शेअर करणे संपले आहे.",
    },
    "unavailable": {
        "en": "Your location hasn't updated for a while. Open the app to check.",
        "hi": "आपका स्थान कुछ समय से अपडेट नहीं हुआ है। जाँचने के लिए ऐप खोलें।",
        "mr": "तुमचे स्थान काही काळ अपडेट झालेले नाही. तपासण्यासाठी अॅप उघडा.",
    },
}


class LocationError(Exception):
    def __init__(self, message, field="non_field_errors"):
        super().__init__(message)
        self.message = message
        self.field = field


def _notify(users, event, family_id):
    """Never for a position, never with coordinates, and never blocking."""
    users = [u for u in users if u]
    if not users:
        return

    def build(language):
        return _TITLE[language], _BODY[event][language]

    try:
        send_localized(
            "family_location", build, users=users,
            data={"type": "family_location", "route": "/familyMap", "family_id": str(family_id)},
            inbox={"category": "family_location"},
        )
    except Exception as exc:
        logger.warning("Location notice failed (%s).", type(exc).__name__)


def _viewer_users(session):
    return list(
        session.recipients.filter(revoked_at__isnull=True, member__user__isnull=False)
        .values_list("member__user_id", flat=True)
    )


def _end(session, status, by):
    """The position goes in the same step as the session."""
    MemberLocation.objects.filter(session=session).delete()
    session.status = status
    session.ended_at = timezone.now()
    session.save(update_fields=["status", "ended_at"])
    audit(session.family, by, f"location_{status}", session.member)


def settle(session):
    """Ends the session if its time has passed. Returns it, current."""
    if session.status in LocationSession.OPEN and session.expires_at <= timezone.now():
        with transaction.atomic():
            locked = LocationSession.objects.select_for_update().get(pk=session.pk)
            if locked.status in LocationSession.OPEN:
                _end(locked, LocationSession.Status.EXPIRED, None)
                users = [*_viewer_users(locked), locked.started_by_id]
                transaction.on_commit(lambda: _notify(users, "expired", locked.family_id))
        session.refresh_from_db()
    return session


def expiry_for(minutes, until_stopped):
    limit = settings.LOCATION_MAX_SHARE_HOURS * 60
    if until_stopped:
        return timezone.now() + timedelta(minutes=limit)
    if minutes not in STANDARD_MINUTES:
        raise LocationError("Choose a sharing time.", "duration_minutes")
    return timezone.now() + timedelta(minutes=min(minutes, limit))


def _grant(session, members):
    for member in members:
        row, created = LocationRecipient.objects.get_or_create(session=session, member=member)
        if not created and row.revoked_at:
            row.revoked_at = None
            row.save(update_fields=["revoked_at"])


@transaction.atomic
def start(family, member, by, recipients, expires_at):
    existing = LocationSession.objects.select_for_update().filter(
        Q(member=member) | Q(started_by=by), status__in=LocationSession.OPEN,
    )
    if any(settle(s).status in LocationSession.OPEN for s in existing):
        raise LocationError("Sharing is already on.")
    try:
        with transaction.atomic():
            session = LocationSession.objects.create(
                family=family, member=member, started_by=by, expires_at=expires_at,
            )
    except IntegrityError as exc:
        raise LocationError("Sharing is already on.") from exc
    _grant(session, recipients)
    audit(family, by, "location_started", member, viewers=len(recipients))
    users = _viewer_users(session)
    transaction.on_commit(lambda: _notify(users, "started", family.pk))
    return session


def _open_session(session):
    session = settle(session)
    if session.status not in LocationSession.OPEN:
        raise LocationError("This sharing session has ended.")
    return session


def pause(session, by):
    session = _open_session(session)
    if session.status == LocationSession.Status.ACTIVE:
        session.status = LocationSession.Status.PAUSED
        session.paused_at = timezone.now()
        session.save(update_fields=["status", "paused_at"])
        audit(session.family, by, "location_paused", session.member)
    return session


def resume(session, by):
    session = _open_session(session)
    if session.status == LocationSession.Status.PAUSED:
        session.status = LocationSession.Status.ACTIVE
        session.paused_at = None
        session.save(update_fields=["status", "paused_at"])
        audit(session.family, by, "location_resumed", session.member)
    return session


@transaction.atomic
def stop(session, by):
    session = settle(session)
    if session.status in LocationSession.OPEN:
        _end(session, LocationSession.Status.STOPPED, by)
        users = _viewer_users(session)
        transaction.on_commit(lambda: _notify(users, "stopped", session.family_id))
    return session


@transaction.atomic
def set_recipients(session, by, members):
    session = _open_session(session)
    wanted = {m.pk for m in members}
    now = timezone.now()
    session.recipients.filter(revoked_at__isnull=True).exclude(member_id__in=wanted).update(revoked_at=now)
    _grant(session, members)
    audit(session.family, by, "location_recipients_changed", session.member, viewers=len(wanted))
    return session


def extend(session, by, expires_at):
    session = _open_session(session)
    session.expires_at = expires_at
    session.save(update_fields=["expires_at"])
    audit(session.family, by, "location_duration_changed", session.member)
    return session


def record_update(session, data):
    """Returns True if stored. An older or repeated fix changes nothing, so a
    late upload can never replace a newer position."""
    session = settle(session)
    if session.status == LocationSession.Status.PAUSED:
        raise LocationError("Sharing is paused.")
    if session.status != LocationSession.Status.ACTIVE:
        raise LocationError("This sharing session has ended.")
    with transaction.atomic():
        current = MemberLocation.objects.select_for_update().filter(session=session).first()
        if current and data["captured_at"] <= current.captured_at:
            return False
        MemberLocation.objects.update_or_create(session=session, defaults=data)
        if session.stale_notified_at:
            session.stale_notified_at = None
            session.save(update_fields=["stale_notified_at"])
    return True


def freshness(location):
    """Based only on when the phone took the fix. Nothing is estimated."""
    if location is None:
        return "unavailable"
    age = (timezone.now() - location.captured_at).total_seconds()
    if age <= settings.LOCATION_LIVE_SECONDS:
        return "live"
    if age <= settings.LOCATION_RECENT_SECONDS:
        return "recent"
    return "last_known"


def sweep():
    """Run on a schedule by Celery beat."""
    now = timezone.now()
    due = LocationSession.objects.filter(status__in=LocationSession.OPEN, expires_at__lte=now)
    ended = 0
    for session in due[:500]:
        settle(session)
        ended += 1
    quiet_since = now - timedelta(minutes=settings.LOCATION_STALE_NOTICE_MINUTES)
    stale = LocationSession.objects.filter(
        status=LocationSession.Status.ACTIVE, stale_notified_at__isnull=True, created_at__lte=quiet_since,
    ).select_related("location")
    for session in stale[:500]:
        location = getattr(session, "location", None)
        if location is None or location.captured_at <= quiet_since:
            session.stale_notified_at = now
            session.save(update_fields=["stale_notified_at"])
            _notify([session.started_by_id], "unavailable", session.family_id)
    keep_until = now - timedelta(days=settings.LOCATION_SESSION_RETENTION_DAYS)
    LocationSession.objects.exclude(status__in=LocationSession.OPEN).filter(ended_at__lte=keep_until).delete()
    return ended
