"""
Family location API (all under /api/location/, JWT required). Nothing here is
public. Outsiders get 404 through the family lookup, and anyone not chosen gets
no sign that a session exists. Coordinates are never logged or audited.
"""

import uuid
from datetime import timedelta

from django.conf import settings
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers as drf, status
from rest_framework.throttling import UserRateThrottle

from apps.family.views import audit, error, forbidden, ok
from apps.familylocation import policy, services
from apps.familylocation.models import LocationSession
from apps.familylocation.services import LocationError
from apps.lostfound import policy as case_policy
from apps.lostfound.models import ACTIVE_STATUSES, LostFoundCase
from apps.safety.views import _Safety


class UpdateThrottle(UserRateThrottle):
    scope = "location_update"
    rate = "360/hour"


class FeedThrottle(UserRateThrottle):
    scope = "location_feed"
    rate = "720/hour"


class StartSerializer(drf.Serializer):
    member_id = drf.UUIDField(required=False, allow_null=True)
    recipient_ids = drf.ListField(child=drf.UUIDField(), allow_empty=False)
    duration_minutes = drf.IntegerField(required=False, allow_null=True)
    until_stopped = drf.BooleanField(required=False, default=False)
    consent = drf.BooleanField()

    def validate_consent(self, value):
        if not value:
            raise drf.ValidationError("Sharing needs your agreement.")
        return value


class UpdateSerializer(drf.Serializer):
    latitude = drf.DecimalField(max_digits=9, decimal_places=6, min_value=-90, max_value=90)
    longitude = drf.DecimalField(max_digits=9, decimal_places=6, min_value=-180, max_value=180)
    accuracy_m = drf.FloatField(required=False, allow_null=True, min_value=0)
    speed_mps = drf.FloatField(required=False, allow_null=True, min_value=0)
    heading = drf.FloatField(required=False, allow_null=True, min_value=0, max_value=360)
    captured_at = drf.DateTimeField()

    def validate_captured_at(self, value):
        if value > timezone.now() + timedelta(minutes=2):
            raise drf.ValidationError("This time is in the future.")
        return value

    def validate(self, attrs):
        if attrs["latitude"] == 0 and attrs["longitude"] == 0:
            raise drf.ValidationError({"latitude": "That isn't a real position."})
        return attrs


def _session_body(session, user):
    location = getattr(session, "location", None)
    remaining = (session.expires_at - timezone.now()).total_seconds()
    grants = session.recipients.filter(revoked_at__isnull=True).select_related("member__user")
    return {
        "id": str(session.pk),
        "member_id": str(session.member_id),
        "member_name": session.member.display_name,
        "status": session.status,
        "reports_from_me": session.started_by_id == user.pk,
        "expires_at": session.expires_at,
        "remaining_seconds": max(int(remaining), 0),
        "last_update": location.captured_at if location else None,
        "recipients": [
            {"member_id": str(g.member_id), "name": g.member.display_name, "last_viewed_at": g.last_viewed_at}
            for g in grants
        ],
        "update_seconds": settings.LOCATION_UPDATE_SECONDS,
        "distance_metres": settings.LOCATION_DISTANCE_METRES,
    }


class _Location(_Safety):
    def session_for(self, request, session_id):
        """The session and the requester's membership, or (None, None) so a
        session outside someone's family looks the same as none at all."""
        session = get_object_or_404(LocationSession.objects.select_related("member__user", "family"), pk=session_id)
        actor = session.family.members.filter(user=request.user).first()
        return (session, actor) if actor else (None, None)

    def managed(self, request, session_id):
        session, actor = self.session_for(request, session_id)
        if session is None or not policy.can_manage(actor, session):
            return None
        return session

    def chosen(self, actor, member, ids):
        """Only eligible people. Anything else in the list is refused."""
        people = list(policy.eligible_viewers(member).filter(pk__in=ids))
        return people if len(people) == len(set(ids)) else None

    def nothing(self):
        return error({"detail": "Not found."}, status.HTTP_404_NOT_FOUND)

    def run(self, request, action):
        try:
            return ok(_session_body(action(), request.user))
        except LocationError as refused:
            return error({refused.field: [refused.message]}, status.HTTP_409_CONFLICT)


class EligibleAPI(_Location):
    def get(self, request, family_id):
        actor = self.actor_for(request, family_id)
        member = self.member(actor, request.query_params.get("member_id") or actor.pk)
        if not policy.can_start_for(actor, member):
            return forbidden()
        return ok({
            "max_hours": settings.LOCATION_MAX_SHARE_HOURS,
            "people": [
                {"member_id": str(m.pk), "name": m.display_name, "relationship": m.relationship}
                for m in policy.eligible_viewers(member)
            ],
        })


class SessionListAPI(_Location):
    def get(self, request, family_id):
        """Sessions this person controls."""
        actor = self.actor_for(request, family_id)
        sessions = LocationSession.objects.filter(
            family=actor.family, status__in=LocationSession.OPEN,
        ).select_related("member__user", "location")
        mine = [
            s for s in (services.settle(s) for s in sessions)
            if s.status in LocationSession.OPEN and policy.can_manage(actor, s)
        ]
        return ok([_session_body(s, request.user) for s in mine])

    def post(self, request, family_id):
        if self._insecure:
            return self.handle_insecure()
        actor = self.actor_for(request, family_id)
        serializer = StartSerializer(data=request.data)
        if not serializer.is_valid():
            return error(serializer.errors)
        data = serializer.validated_data
        member = self.member(actor, data.get("member_id") or actor.pk)
        if not policy.can_start_for(actor, member):
            return forbidden()
        recipients = self.chosen(actor, member, data["recipient_ids"])
        if recipients is None:
            return error({"recipient_ids": ["Choose people from your family."]})
        try:
            expires_at = services.expiry_for(data.get("duration_minutes"), data["until_stopped"])
            session = services.start(actor.family, member, request.user, recipients, expires_at)
        except LocationError as refused:
            return error({refused.field: [refused.message]}, status.HTTP_409_CONFLICT)
        return ok(_session_body(session, request.user), status.HTTP_201_CREATED)


class SessionDetailAPI(_Location):
    def get(self, request, session_id):
        session = self.managed(request, session_id)
        if session is None:
            return self.nothing()
        return ok(_session_body(services.settle(session), request.user))


class SessionPauseAPI(_Location):
    def post(self, request, session_id):
        session = self.managed(request, session_id)
        if session is None:
            return self.nothing()
        return self.run(request, lambda: services.pause(session, request.user))


class SessionResumeAPI(_Location):
    def post(self, request, session_id):
        session = self.managed(request, session_id)
        if session is None:
            return self.nothing()
        return self.run(request, lambda: services.resume(session, request.user))


class SessionStopAPI(_Location):
    def post(self, request, session_id):
        session = self.managed(request, session_id)
        if session is None:
            return self.nothing()
        return self.run(request, lambda: services.stop(session, request.user))


class SessionRecipientsAPI(_Location):
    def post(self, request, session_id):
        session = self.managed(request, session_id)
        if session is None:
            return self.nothing()
        ids = request.data.get("recipient_ids")
        if not isinstance(ids, list) or not ids:
            return error({"recipient_ids": ["Choose at least one person."]})
        try:
            recipients = self.chosen(None, session.member, [uuid.UUID(str(i)) for i in ids])
        except ValueError:
            recipients = None
        if recipients is None:
            return error({"recipient_ids": ["Choose people from your family."]})
        return self.run(request, lambda: services.set_recipients(session, request.user, recipients))


class SessionDurationAPI(_Location):
    def post(self, request, session_id):
        session = self.managed(request, session_id)
        if session is None:
            return self.nothing()
        minutes = request.data.get("duration_minutes")
        until_stopped = request.data.get("until_stopped") is True

        def change():
            return services.extend(session, request.user, services.expiry_for(minutes, until_stopped))

        return self.run(request, change)


class LocationUpdateAPI(_Location):
    """From the phone that started the session, and no other account."""

    throttle_classes = [UpdateThrottle]

    def post(self, request, session_id):
        if self._insecure:
            return self.handle_insecure()
        session, actor = self.session_for(request, session_id)
        if session is None or session.started_by_id != request.user.pk:
            return self.nothing()
        serializer = UpdateSerializer(data=request.data)
        if not serializer.is_valid():
            return error(serializer.errors)
        try:
            accepted = services.record_update(session, serializer.validated_data)
        except LocationError as refused:
            session.refresh_from_db()
            return _ended(session, refused.message)
        return ok({"accepted": accepted, "status": LocationSession.Status.ACTIVE})


def _ended(session, message):
    """Tells the phone to stop collecting."""
    return error({"detail": message, "status": session.status}, status.HTTP_410_GONE)


def _active_case(request, member):
    """A case the viewer may already see. It grants nothing about location."""
    case = LostFoundCase.objects.filter(
        member=member, case_type="lost", status__in=ACTIVE_STATUSES,
    ).select_related("member").first()
    if case is None or not case_policy.can_view(request.user, case):
        return None
    return {"id": str(case.pk), "reference": case.reference}


def _record_view(request, actor, session):
    """At most hourly: often enough to answer "who looked", without a log of
    every poll. Holds no coordinates."""
    if actor.pk == session.member_id:
        return
    grant = session.recipients.filter(member=actor).first()
    now = timezone.now()
    if grant and (grant.last_viewed_at is None or now - grant.last_viewed_at > timedelta(hours=1)):
        grant.last_viewed_at = now
        grant.save(update_fields=["last_viewed_at"])
        audit(session.family, request.user, "location_viewed", session.member)


def _person(request, actor, session):
    """One person on the map. Coordinates only for a live, unpaused session."""
    location = getattr(session, "location", None)
    body = {
        "member_id": str(session.member_id),
        "name": session.member.display_name,
        "has_photo": hasattr(session.member, "photo"),
        "is_me": session.member_id == actor.pk,
        "state": "paused" if session.status == LocationSession.Status.PAUSED else services.freshness(location),
        "remaining_seconds": max(int((session.expires_at - timezone.now()).total_seconds()), 0),
        "age_seconds": None,
        "captured_at": None,
        "accuracy_m": None,
        "latitude": None,
        "longitude": None,
        "case": _active_case(request, session.member),
    }
    if session.status == LocationSession.Status.ACTIVE and location is not None:
        body.update({
            "age_seconds": max(int((timezone.now() - location.captured_at).total_seconds()), 0),
            "captured_at": location.captured_at,
            "accuracy_m": location.accuracy_m,
            "latitude": float(location.latitude),
            "longitude": float(location.longitude),
        })
    return body


class FeedAPI(_Location):
    throttle_classes = [FeedThrottle]

    def get(self, request, family_id):
        if self._insecure:
            return self.handle_insecure()
        actor = self.actor_for(request, family_id)
        sessions = LocationSession.objects.filter(
            family=actor.family, status__in=LocationSession.OPEN,
        ).select_related("member__user", "member__photo", "location")
        people = []
        for session in sessions:
            session = services.settle(session)
            if session.status not in LocationSession.OPEN or not policy.can_view(actor, session):
                continue
            _record_view(request, actor, session)
            people.append(_person(request, actor, session))
        recently = timezone.now() - timedelta(minutes=30)
        ended = LocationSession.objects.filter(
            family=actor.family, status__in=["stopped", "expired"], ended_at__gte=recently,
            recipients__member=actor, recipients__revoked_at__isnull=True,
        ).select_related("member__user").distinct()
        response = ok({
            "poll_seconds": settings.LOCATION_POLL_SECONDS,
            "live_seconds": settings.LOCATION_LIVE_SECONDS,
            "recent_seconds": settings.LOCATION_RECENT_SECONDS,
            "people": people,
            "ended": [
                {"member_id": str(s.member_id), "name": s.member.display_name, "state": s.status}
                for s in ended
            ],
        })
        response["Cache-Control"] = "no-store"
        return response


class CaseLocationAPI(_Location):
    """For a Lost & Found case. Returns a position only if this person was
    already chosen for an open session. A report overrides nothing."""

    def get(self, request, case_id):
        case = get_object_or_404(LostFoundCase.objects.select_related("member__user"), pk=case_id)
        if not case_policy.can_view(request.user, case) or case.member_id is None:
            return self.nothing()
        actor = case.family.members.filter(user=request.user).first() if case.family_id else None
        if actor is None:
            return ok({"state": "not_shared"})
        session = LocationSession.objects.filter(
            member=case.member, status__in=LocationSession.OPEN,
        ).select_related("member__user", "location").first()
        if session is not None:
            session = services.settle(session)
        if session is None or session.status not in LocationSession.OPEN or not policy.can_view(actor, session):
            return ok({"state": "not_shared"})
        _record_view(request, actor, session)
        response = ok(_person(request, actor, session))
        response["Cache-Control"] = "no-store"
        return response
