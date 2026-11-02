"""
Emergency SOS API (all under /api/emergency/, JWT required). Nothing here is
public, and anyone without access gets 404. Positions and phone numbers are
never logged or audited, and the app is told plainly that no emergency service
is contacted by any of this.
"""

from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers as drf, status
from rest_framework.throttling import UserRateThrottle

from apps.emergency import policy, services
from apps.emergency.models import ACTIVE_STATUSES, EmergencySOS, EmergencyUpdate, Status
from apps.emergency.services import ActiveExists, EmergencyError
from apps.family.views import error, forbidden, ok
from apps.safety.views import _Safety

PAGE_SIZE = 20


class SosThrottle(UserRateThrottle):
    """High enough that it can't stand between someone and help. A blocked
    request still gets the call option on screen."""

    scope = "emergency_sos"
    rate = "30/hour"


class ChangeThrottle(UserRateThrottle):
    scope = "emergency_change"
    rate = "60/hour"


class ContactThrottle(UserRateThrottle):
    scope = "emergency_contact"
    rate = "20/hour"


class _Place(drf.Serializer):
    latitude = drf.DecimalField(max_digits=9, decimal_places=6, min_value=-90, max_value=90, required=False, allow_null=True)
    longitude = drf.DecimalField(max_digits=9, decimal_places=6, min_value=-180, max_value=180, required=False, allow_null=True)
    accuracy_m = drf.FloatField(required=False, allow_null=True, min_value=0)
    location_at = drf.DateTimeField(required=False, allow_null=True)
    location_text = drf.CharField(max_length=240, required=False, allow_blank=True)

    def validate_location_at(self, value):
        if value and value > timezone.now() + timedelta(minutes=2):
            raise drf.ValidationError("This time is in the future.")
        return value

    def validate(self, attrs):
        if (attrs.get("latitude") is None) != (attrs.get("longitude") is None):
            raise drf.ValidationError({"latitude": "Send both coordinates, or neither."})
        if attrs.get("latitude") == 0 and attrs.get("longitude") == 0:
            raise drf.ValidationError({"latitude": "That isn't a real position."})
        if attrs.get("latitude") is None:
            for field in ("latitude", "longitude", "accuracy_m", "location_at"):
                attrs.pop(field, None)
        return {k: v for k, v in attrs.items() if v is not None}


class CreateSerializer(_Place):
    client_id = drf.UUIDField()
    category = drf.ChoiceField(choices=EmergencySOS.Category.choices)
    details = drf.CharField(max_length=1000, required=False, allow_blank=True)
    written_at = drf.DateTimeField(required=False, allow_null=True)


class BodySerializer(drf.Serializer):
    body = drf.CharField(max_length=1000)


class ReasonSerializer(drf.Serializer):
    reason = drf.CharField(max_length=300)


def _timeline(sos):
    return [
        {"status": h.to_status, "from_status": h.from_status, "at": h.created_at, "by": h.actor_role}
        for h in sos.history.all()
    ]


def _updates(sos, role):
    rows = sos.updates.all()
    if role != "ops":
        rows = rows.filter(kind__in=EmergencyUpdate.VISIBLE)
    return [{"kind": u.kind, "body": u.body, "at": u.created_at} for u in rows]


def _recipients(sos):
    """Each stage is its own field, because they mean different things."""
    rows = sos.recipients.select_related("member__user", "notification__delivery")
    out = []
    for row in rows:
        notification = row.notification
        delivery = getattr(notification, "delivery", None) if notification else None
        out.append({
            "name": row.member.display_name,
            "notification": delivery.state if delivery else "pending",
            "reached_app_at": notification.delivered_at if notification else None,
            "acknowledged_at": row.acknowledged_at,
        })
    return out


def sos_body(sos, role, user):
    place = policy.can_see_location(role, sos)
    responder_ack = sos.history.filter(to_status=Status.ACKNOWLEDGED).first()
    mine = policy.recipient_row(user, sos) if role == "family" else None
    return {
        "id": str(sos.pk),
        "reference": sos.reference,
        "category": sos.category,
        "status": sos.status,
        "is_active": sos.is_active,
        "role": role,
        "person_name": sos.user.full_Name,
        "details": sos.details,
        "created_at": sos.created_at,
        "updated_at": sos.updated_at,
        "written_at": sos.written_at,
        "location_text": sos.location_text if place else "",
        "latitude": float(sos.latitude) if place and sos.latitude is not None else None,
        "longitude": float(sos.longitude) if place and sos.longitude is not None else None,
        "accuracy_m": sos.accuracy_m if place else None,
        "location_at": sos.location_at if place else None,
        "cancel_reason": sos.cancel_reason if role != "family" else "",
        "resolution_note": sos.resolution_note,
        "responder_acknowledged_at": responder_ack.created_at if responder_ack else None,
        "timeline": _timeline(sos),
        "updates": _updates(sos, role),
        "family": _recipients(sos) if role in ("owner", "ops") else [],
        "i_acknowledged": bool(mine and mine.acknowledged_at),
    }


def _row(sos):
    return {
        "id": str(sos.pk), "reference": sos.reference, "category": sos.category, "status": sos.status,
        "is_active": sos.is_active, "person_name": sos.user.full_Name, "created_at": sos.created_at,
        "updated_at": sos.updated_at,
    }


def _page(request, rows):
    page = Paginator(rows, PAGE_SIZE).get_page(request.query_params.get("page"))
    return ok({"results": [_row(s) for s in page], "count": page.paginator.count, "has_next": page.has_next()})


class _Emergency(_Safety):
    def find(self, request, sos_id):
        """The SOS and the requester's role, or (None, None) for no access."""
        sos = get_object_or_404(EmergencySOS.objects.select_related("user"), pk=sos_id)
        role = policy.role_for(request.user, sos)
        return (sos, role) if role else (None, None)

    def nothing(self):
        return error({"detail": "Not found."}, status.HTTP_404_NOT_FOUND)

    def done(self, request, sos, role):
        sos.refresh_from_db()
        response = ok(sos_body(sos, role, request.user))
        response["Cache-Control"] = "no-store"
        return response

    def refuse(self, problem):
        return error({problem.field: [problem.message]}, status.HTTP_409_CONFLICT)


class MeAPI(_Emergency):
    """What the SOS screen needs. `dispatch_integration` is false until a real
    one exists, and the app says so."""

    def get(self, request):
        active = EmergencySOS.objects.filter(user=request.user, status__in=ACTIVE_STATUSES).first()
        people = {m.user_id: m.display_name for m in policy.family_members_to_tell(request.user)}
        return ok({
            "active": _row(active) if active else None,
            "family": sorted(people.values()),
            "emergency_numbers": settings.EMERGENCY_NUMBERS,
            "dispatch_integration": False,
        })


class SosListAPI(_Emergency):
    def get_throttles(self):
        return [SosThrottle()] if self.request.method == "POST" else []

    def get(self, request):
        if request.query_params.get("scope") == "family":
            rows = EmergencySOS.objects.filter(recipients__member__user=request.user).select_related("user").distinct()
        else:
            rows = EmergencySOS.objects.filter(user=request.user).select_related("user")
        return _page(request, rows)

    def post(self, request):
        if self._insecure:
            return self.handle_insecure()
        serializer = CreateSerializer(data=request.data)
        if not serializer.is_valid():
            return error(serializer.errors)
        try:
            sos, created = services.create_sos(request.user, serializer.validated_data)
        except ActiveExists as open_one:
            body = {"non_field_errors": ["You already have an active SOS."], "active_id": str(open_one.sos.pk)}
            return error(body, status.HTTP_409_CONFLICT)
        sos.refresh_from_db()
        response = ok(sos_body(sos, "owner", request.user), status.HTTP_201_CREATED if created else status.HTTP_200_OK)
        response["Cache-Control"] = "no-store"
        return response


class SosDetailAPI(_Emergency):
    def get(self, request, sos_id):
        sos, role = self.find(request, sos_id)
        if sos is None:
            return self.nothing()
        if role == "ops":
            services.audit(sos, request.user, "viewed")
        return self.done(request, sos, role)


class _OwnerAction(_Emergency):
    throttle_classes = [ChangeThrottle]

    def owned(self, request, sos_id):
        sos, role = self.find(request, sos_id)
        return (sos, role, None) if role == "owner" else (None, None, self.nothing() if role is None else forbidden())


class SosCancelAPI(_OwnerAction):
    def post(self, request, sos_id):
        sos, role, refused = self.owned(request, sos_id)
        if refused:
            return refused
        serializer = ReasonSerializer(data=request.data)
        if not serializer.is_valid():
            return error(serializer.errors)
        try:
            services.cancel(sos, request.user, serializer.validated_data["reason"])
        except EmergencyError as problem:
            return self.refuse(problem)
        return self.done(request, sos, role)


class SosInfoAPI(_OwnerAction):
    def post(self, request, sos_id):
        sos, role, refused = self.owned(request, sos_id)
        if refused:
            return refused
        serializer = BodySerializer(data=request.data)
        if not serializer.is_valid():
            return error(serializer.errors)
        try:
            services.add_info(sos, request.user, serializer.validated_data["body"])
        except EmergencyError as problem:
            return self.refuse(problem)
        return self.done(request, sos, role)


class SosLocationAPI(_OwnerAction):
    def post(self, request, sos_id):
        sos, role, refused = self.owned(request, sos_id)
        if refused:
            return refused
        serializer = _Place(data=request.data)
        if not serializer.is_valid():
            return error(serializer.errors)
        data = serializer.validated_data
        if "latitude" not in data and not data.get("location_text", "").strip():
            return error({"location_text": ["Add a position or describe where you are."]})
        try:
            services.update_location(sos, request.user, data)
        except EmergencyError as problem:
            return self.refuse(problem)
        return self.done(request, sos, role)


class SosFamilyAckAPI(_Emergency):
    """A relative saying they've seen it. It changes no status, and it's never
    shown as a responder."""

    throttle_classes = [ChangeThrottle]

    def post(self, request, sos_id):
        sos, role = self.find(request, sos_id)
        if sos is None:
            return self.nothing()
        row = policy.recipient_row(request.user, sos)
        if row is None:
            return forbidden()
        services.family_acknowledge(sos, row)
        return self.done(request, sos, role)


class SosContactAPI(_Emergency):
    """The person's number, one at a time and logged, so the app can dial it
    without ever listing it. Sending an SOS is what allows this."""

    throttle_classes = [ContactThrottle]

    def post(self, request, sos_id):
        sos, role = self.find(request, sos_id)
        if sos is None:
            return self.nothing()
        if role not in ("family", "ops") or not sos.is_active:
            return forbidden()
        services.audit(sos, request.user, "contact_used", role=role)
        response = ok({"phone": sos.user.phone_number})
        response["Cache-Control"] = "no-store"
        return response


class _Ops(_Emergency):
    """The foundation for Phase 7. Family and pilgrims get 403 before anything
    is looked up, and a help desk reaches only what's assigned to it."""

    throttle_classes = [ChangeThrottle]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        self._allowed = policy.is_operator(request.user)

    def target(self, request, sos_id):
        if not self._allowed:
            return None, forbidden()
        sos = get_object_or_404(EmergencySOS.objects.select_related("user"), pk=sos_id)
        return (sos, None) if policy.can_operate(request.user, sos) else (None, self.nothing())

    def act(self, request, sos_id, action):
        sos, refused = self.target(request, sos_id)
        if refused:
            return refused
        try:
            action(sos)
        except EmergencyError as problem:
            return self.refuse(problem)
        return self.done(request, sos, "ops")

    def body(self, request):
        return str(request.data.get("body") or "").strip()[:1000]


class OpsListAPI(_Ops):
    def get(self, request):
        if not self._allowed:
            return forbidden()
        rows = policy.ops_scope(request.user, EmergencySOS.objects.select_related("user"))
        for field in ("category", "status"):
            value = request.query_params.get(field)
            if value:
                rows = rows.filter(**{field: value})
        return _page(request, rows)


class OpsDetailAPI(_Ops):
    def get(self, request, sos_id):
        sos, refused = self.target(request, sos_id)
        if refused:
            return refused
        services.audit(sos, request.user, "viewed")
        return self.done(request, sos, "ops")


class OpsAcknowledgeAPI(_Ops):
    def post(self, request, sos_id):
        return self.act(request, sos_id, lambda sos: services.acknowledge(sos, request.user))


class OpsCoordinateAPI(_Ops):
    def post(self, request, sos_id):
        remarks = self.body(request)
        if not remarks:
            return error({"body": ["Say what was coordinated."]})
        return self.act(request, sos_id, lambda sos: services.coordinate(sos, request.user, remarks))


class OpsUpdateAPI(_Ops):
    def post(self, request, sos_id):
        text = self.body(request)
        if not text:
            return error({"body": ["Write an update."]})
        internal = request.data.get("internal") is True
        return self.act(request, sos_id, lambda sos: services.responder_update(sos, request.user, text, internal))


class OpsEscalateAPI(_Ops):
    def post(self, request, sos_id):
        reason = self.body(request)
        if not reason:
            return error({"body": ["Say why this needs escalating."]})
        return self.act(request, sos_id, lambda sos: services.escalate(sos, request.user, reason))


class OpsAssignAPI(_Ops):
    def post(self, request, sos_id):
        if not self._allowed:
            return forbidden()
        if not policy.can_operate(request.user, EmergencySOS(assigned_to=None)):
            return forbidden()
        try:
            assignee = get_user_model().objects.filter(pk=request.data.get("assignee_id")).first()
        except (ValidationError, ValueError, TypeError):
            assignee = None
        if assignee is None:
            return error({"assignee_id": ["Choose an authorized responder."]})
        return self.act(request, sos_id, lambda sos: services.assign(sos, request.user, assignee))


class OpsResolveAPI(_Ops):
    def post(self, request, sos_id):
        note = self.body(request)
        if not note:
            return error({"body": ["Say how this was resolved."]})
        return self.act(request, sos_id, lambda sos: services.resolve(sos, request.user, note))


class OpsCloseAPI(_Ops):
    def post(self, request, sos_id):
        return self.act(request, sos_id, lambda sos: services.close(sos, request.user, self.body(request)))
