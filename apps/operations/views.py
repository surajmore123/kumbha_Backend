"""
Volunteer and safety operations (all under /api/operations/). Everything except
sign-in needs a token, and every check is made here on each request from the
live account, so nothing the app sends can raise anyone's access.

Case and SOS actions that already existed stay on their own routes.
"""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers as drf, status
from rest_framework.permissions import AllowAny
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from apps.aiChat.services.geo import distance_km
from apps.emergency import policy as sos_policy
from apps.emergency.models import ACTIVE_STATUSES as SOS_ACTIVE, EmergencySOS
from apps.family.views import error, forbidden, ok
from apps.lostfound import policy as case_policy
from apps.lostfound.models import ACTIVE_STATUSES, LostFoundCase
from apps.lostfound.services import add_note, audit as case_audit
from apps.operations import services
from apps.operations.models import CaseAssignment
from apps.operations.services import OperationsError
from apps.reunification.models import MeetingPoint
from apps.safety import policy as safety_policy
from apps.safety.models import SafetyHelper
from apps.safety.views import _Safety

Status = CaseAssignment.Status
PAGE_SIZE = 25
ROLE_NAMES = {
    SafetyHelper.Role.VOLUNTEER: "VOLUNTEER",
    SafetyHelper.Role.HELP_DESK: "HELP_DESK_OPERATOR",
    SafetyHelper.Role.SAFETY_STAFF: "SAFETY_COORDINATOR",
}
_LOCK_AFTER = 5
_LOCK_SECONDS = 900


class SignInThrottle(AnonRateThrottle):
    scope = "operations_sign_in"
    rate = "20/hour"


def _phone(raw):
    value = str(raw or "").strip()
    if value.startswith("+91"):
        value = value[3:]
    elif value.startswith("91") and len(value) == 12:
        value = value[2:]
    return f"+91{value}" if value.isdigit() and len(value) == 10 and value[0] in "6789" else None


def _tokens(user):
    user.last_login = timezone.now()
    user.save(update_fields=["last_login"])
    return ok({
        "user_id": str(user.pk),
        "phone_number": user.phone_number,
        "access_token": str(RefreshToken.for_user(user).access_token),
        "session_id": None,
    })


class _SignIn(APIView):
    """Same answer for a wrong phone and a wrong secret, and a short lock after
    repeated failures, so accounts can't be probed or guessed."""

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [SignInThrottle]

    def account(self, request):
        phone = _phone(request.data.get("phone_number"))
        return None if phone is None else (
            SafetyHelper.objects.select_related("user").filter(user__phone_number=phone).first()
        )

    def locked(self, request):
        return cache.get(self.lock_key(request), 0) >= _LOCK_AFTER

    def lock_key(self, request):
        return f"ops_sign_in:{_phone(request.data.get('phone_number'))}"

    def failed(self, request):
        key = self.lock_key(request)
        cache.set(key, cache.get(key, 0) + 1, _LOCK_SECONDS)
        return error({"detail": "Those details don't match."}, status.HTTP_401_UNAUTHORIZED)

    def blocked(self):
        return error({"detail": "Too many attempts. Try again later."}, status.HTTP_429_TOO_MANY_REQUESTS)


class SetupAPI(_SignIn):
    """First sign-in: the code an administrator handed over, and a new password."""

    def post(self, request):
        if self.locked(request):
            return self.blocked()
        helper = self.account(request)
        code = str(request.data.get("code") or "").strip().upper()
        allowed = (SafetyHelper.Status.PENDING, SafetyHelper.Status.ACTIVE)
        if helper is None or helper.status not in allowed or not services.setup_is_valid(helper, code):
            return self.failed(request)
        password = str(request.data.get("password") or "")
        try:
            validate_password(password, helper.user)
        except ValidationError as problem:
            return error({"password": list(problem.messages)})
        services.complete_setup(helper, password)
        cache.delete(self.lock_key(request))
        return _tokens(helper.user)


class PasswordLoginAPI(_SignIn):
    def post(self, request):
        if self.locked(request):
            return self.blocked()
        helper = self.account(request)
        password = str(request.data.get("password") or "")
        allowed = (SafetyHelper.Status.PENDING, SafetyHelper.Status.ACTIVE)
        if helper is not None:
            user = helper.user if helper.status in allowed else None
        else:
            # Administrators have no OTP sign-in either, so they use their
            # existing Django password here.
            phone = _phone(request.data.get("phone_number"))
            user = get_user_model().objects.filter(phone_number=phone, is_staff=True).first() if phone else None
        if user is None or not user.is_active or not user.check_password(password):
            return self.failed(request)
        cache.delete(self.lock_key(request))
        return _tokens(user)


class AvailabilitySerializer(drf.Serializer):
    availability = drf.ChoiceField(choices=SafetyHelper.Availability.choices)


class ProgressSerializer(drf.Serializer):
    status = drf.ChoiceField(choices=[Status.ACCEPTED, Status.IN_PROGRESS, Status.COMPLETED])


class TextSerializer(drf.Serializer):
    body = drf.CharField(max_length=1000)


class ReasonSerializer(drf.Serializer):
    reason = drf.CharField(max_length=500)


class AssignSerializer(drf.Serializer):
    volunteer_id = drf.UUIDField()
    notes = drf.CharField(max_length=500, required=False, allow_blank=True)


def _zone(zone):
    return {"id": str(zone.pk), "code": zone.code, "name": zone.name}


def _assignment(row):
    return {
        "id": str(row.pk),
        "status": row.status,
        "notes": row.notes,
        "escalation_reason": row.escalation_reason,
        "volunteer_id": str(row.volunteer_id),
        "volunteer_name": row.volunteer.full_Name or "",
        "assigned_at": row.assigned_at,
        "updated_at": row.updated_at,
        "completed_at": row.completed_at,
    }


def _case_row(case, assignment=None):
    return {
        "id": str(case.pk),
        "reference": case.reference,
        "case_type": case.case_type,
        "status": case.status,
        "priority": "high" if case.is_vulnerable else "normal",
        "location_text": case.location_text,
        "event_at": case.event_at,
        "zone": _zone(case.zone) if case.zone_id else None,
        "assignment": _assignment(assignment) if assignment else None,
    }


def _case_detail(case, assignment):
    """What someone needs to look for a person, and nothing else: no reporter,
    no contact details, no notes, and no exact position for a child or
    vulnerable person."""
    show_place = not case.is_vulnerable
    return {
        **_case_row(case, assignment),
        "person_name": case.person_name,
        "age_min": case.age_min,
        "age_max": case.age_max,
        "physical_description": case.physical_description,
        "clothing_description": case.clothing_description,
        "identifying_marks": case.identifying_marks,
        "safe_facility": case.safe_facility,
        "latitude": float(case.latitude) if show_place and case.latitude is not None else None,
        "longitude": float(case.longitude) if show_place and case.longitude is not None else None,
    }


class _Ops(_Safety):
    def helper(self, request):
        return SafetyHelper.current_for(request.user)

    def nothing(self):
        return error({"detail": "Not found."}, status.HTTP_404_NOT_FOUND)

    def refuse(self, problem):
        return error({problem.field: [problem.message]}, status.HTTP_409_CONFLICT)

    def case(self, case_id):
        return get_object_or_404(LostFoundCase.objects.select_related("zone", "member"), pk=case_id)

    def working(self, request, case):
        """The volunteer's open assignment, or an operator with access."""
        assignment = services.current_assignment(case)
        mine = assignment is not None and assignment.volunteer_id == request.user.pk
        return assignment, (mine or case_policy.can_operate(request.user, case))


class MeAPI(_Ops):
    """The role comes from here and only here. It's read from the account on
    each call, so nothing stored on the phone can change it."""

    def get(self, request):
        helper = SafetyHelper.objects.filter(user=request.user).prefetch_related("zones").first()
        admin = request.user.is_superuser
        if helper is None and not admin:
            return ok({"role": "PILGRIM", "status": None, "user_id": str(request.user.pk)})
        current = admin or (helper is not None and helper.is_current)
        role = helper.role if helper else SafetyHelper.Role.SAFETY_STAFF
        coordinator = current and role == SafetyHelper.Role.SAFETY_STAFF
        desk = current and role == SafetyHelper.Role.HELP_DESK
        return ok({
            "user_id": str(request.user.pk),
            "role": "ADMIN" if admin else ROLE_NAMES[role],
            "status": helper.status if helper else SafetyHelper.Status.ACTIVE,
            "full_name": request.user.full_Name or "",
            "availability": helper.availability if helper else SafetyHelper.Availability.AVAILABLE,
            "zones": [_zone(z) for z in helper.zones.all()] if helper else [],
            "can": {
                "scan": current,
                "report_found": current,
                "manage_cases": coordinator or desk,
                "view_sos": coordinator or desk,
                "assign_cases": coordinator,
                "view_team": coordinator,
            },
        })


class AvailabilityAPI(_Ops):
    def patch(self, request):
        helper = self.helper(request)
        if helper is None:
            return forbidden()
        serializer = AvailabilitySerializer(data=request.data)
        if not serializer.is_valid():
            return error(serializer.errors)
        helper.availability = serializer.validated_data["availability"]
        helper.availability_updated_at = timezone.now()
        helper.save(update_fields=["availability", "availability_updated_at"])
        services.record(request.user, request.user, "availability_changed", availability=helper.availability)
        return ok({"availability": helper.availability})


class OverviewAPI(_Ops):
    def get(self, request):
        if self.helper(request) is None and not request.user.is_superuser:
            return forbidden()
        mine = CaseAssignment.objects.filter(volunteer=request.user)
        body = {
            "active": mine.filter(status__in=CaseAssignment.OPEN).count(),
            "pending": mine.filter(status=Status.ASSIGNED).count(),
            "completed": mine.filter(status=Status.COMPLETED).count(),
        }
        if sos_policy.is_operator(request.user):
            rows = sos_policy.ops_scope(request.user, EmergencySOS.objects.filter(status__in=SOS_ACTIVE))
            body["open_sos"] = rows.count()
            cases = case_policy.ops_scope(request.user, LostFoundCase.objects.filter(status__in=ACTIVE_STATUSES))
            body["open_cases"] = cases.count()
            body["unassigned"] = cases.filter(assigned_to__isnull=True).count()
            body["escalations"] = CaseAssignment.objects.filter(status=Status.ESCALATED, case__in=cases).count()
        return ok(body)


class MyCasesAPI(_Ops):
    def get(self, request):
        if self.helper(request) is None:
            return forbidden()
        rows = CaseAssignment.objects.filter(volunteer=request.user).select_related(
            "case__zone", "case__member", "volunteer",
        )
        state = request.query_params.get("status")
        if state == "open":
            rows = rows.filter(status__in=CaseAssignment.OPEN)
        elif state:
            rows = rows.filter(status=state)
        case_type = request.query_params.get("type")
        if case_type:
            rows = rows.filter(case__case_type=case_type)
        page = Paginator(rows, PAGE_SIZE).get_page(request.query_params.get("page"))
        return ok({
            "results": [_case_row(a.case, a) for a in page],
            "count": page.paginator.count,
            "has_next": page.has_next(),
        })


class CaseDetailAPI(_Ops):
    def get(self, request, case_id):
        case = self.case(case_id)
        assignment, allowed = self.working(request, case)
        if self.helper(request) is None and not request.user.is_superuser or not allowed:
            return self.nothing()
        case_audit(case, request.user, "case_viewed", via="operations")
        response = ok(_case_detail(case, assignment))
        response["Cache-Control"] = "no-store"
        return response


class CaseProgressAPI(_Ops):
    def post(self, request, case_id):
        case = self.case(case_id)
        assignment = services.current_assignment(case)
        if self.helper(request) is None or assignment is None or assignment.volunteer_id != request.user.pk:
            return self.nothing()
        serializer = ProgressSerializer(data=request.data)
        if not serializer.is_valid():
            return error(serializer.errors)
        try:
            services.progress(assignment, serializer.validated_data["status"], request.user)
        except OperationsError as problem:
            return self.refuse(problem)
        return ok(_case_row(case, assignment))


class CaseObservationAPI(_Ops):
    """Goes to staff as an internal note. Nothing reaches the family without review."""

    def post(self, request, case_id):
        case = self.case(case_id)
        assignment, allowed = self.working(request, case)
        if self.helper(request) is None or not allowed:
            return self.nothing()
        serializer = TextSerializer(data=request.data)
        if not serializer.is_valid():
            return error(serializer.errors)
        add_note(case, request.user, "internal", serializer.validated_data["body"])
        return ok(_case_row(case, assignment), status.HTTP_201_CREATED)


class CaseEscalateAPI(_Ops):
    def post(self, request, case_id):
        case = self.case(case_id)
        _, allowed = self.working(request, case)
        if self.helper(request) is None or not allowed:
            return self.nothing()
        serializer = ReasonSerializer(data=request.data)
        if not serializer.is_valid():
            return error(serializer.errors)
        try:
            assignment = services.escalate(case, request.user, serializer.validated_data["reason"])
        except OperationsError as problem:
            return self.refuse(problem)
        return ok(_case_row(case, assignment))


class _Coordinator(_Ops):
    """Safety coordinators and administrators, within their zones."""

    def coordinator(self, request):
        return case_policy.is_staff(request.user)

    def scoped_case(self, request, case_id):
        case = self.case(case_id)
        return case if case_policy.can_operate(request.user, case) else None


class CaseAssignAPI(_Coordinator):
    def post(self, request, case_id):
        if not self.coordinator(request):
            return forbidden()
        case = self.scoped_case(request, case_id)
        if case is None:
            return self.nothing()
        serializer = AssignSerializer(data=request.data)
        if not serializer.is_valid():
            return error(serializer.errors)
        data = serializer.validated_data
        volunteer = get_user_model().objects.filter(pk=data["volunteer_id"]).first()
        if volunteer is None:
            return error({"volunteer_id": ["Choose an approved, active volunteer."]})
        try:
            assignment = services.assign(case, volunteer, request.user, data.get("notes", ""))
        except OperationsError as problem:
            return self.refuse(problem)
        return ok(_case_row(case, assignment), status.HTTP_201_CREATED)


class CaseUnassignAPI(_Coordinator):
    def post(self, request, case_id):
        if not self.coordinator(request):
            return forbidden()
        case = self.scoped_case(request, case_id)
        if case is None:
            return self.nothing()
        try:
            services.unassign(case, request.user, str(request.data.get("reason") or ""))
        except OperationsError as problem:
            return self.refuse(problem)
        return ok(_case_row(case))


class CaseHistoryAPI(_Coordinator):
    def get(self, request, case_id):
        if not self.coordinator(request):
            return forbidden()
        case = self.scoped_case(request, case_id)
        if case is None:
            return self.nothing()
        return ok([_assignment(a) for a in case.assignments.select_related("volunteer")])


class TeamAPI(_Coordinator):
    def get(self, request):
        if not self.coordinator(request):
            return forbidden()
        helpers = SafetyHelper.objects.filter(status=SafetyHelper.Status.ACTIVE, is_active=True).select_related("user")
        if not request.user.is_superuser:
            zones = safety_policy.zone_ids(request.user)
            helpers = helpers.filter(zones__in=zones).distinct()
        return ok([{
            "user_id": str(h.user_id),
            "name": h.user.full_Name or "",
            "role": ROLE_NAMES[h.role],
            "availability": h.availability,
            "zones": [_zone(z) for z in h.zones.all()],
            "open_cases": services.workload(h.user),
        } for h in helpers.prefetch_related("zones")])


class EscalationsAPI(_Coordinator):
    def get(self, request):
        if not self.coordinator(request):
            return forbidden()
        cases = case_policy.ops_scope(request.user, LostFoundCase.objects.all())
        rows = CaseAssignment.objects.filter(status=Status.ESCALATED, case__in=cases).select_related(
            "case__zone", "case__member", "volunteer",
        )
        page = Paginator(rows, PAGE_SIZE).get_page(request.query_params.get("page"))
        return ok({
            "results": [_case_row(a.case, a) for a in page],
            "count": page.paginator.count,
            "has_next": page.has_next(),
        })


class ZonesAPI(_Ops):
    """Your zones, and only verified places inside them."""

    def get(self, request):
        helper = self.helper(request)
        if helper is None and not request.user.is_superuser:
            return forbidden()
        zones = list(helper.zones.filter(is_active=True, del_flag=0)) if helper else []
        points = list(MeetingPoint.objects.filter(status=MeetingPoint.Status.VERIFIED))

        def inside(zone, point):
            radius = zone.radius_m or settings.OPERATIONS_DEFAULT_ZONE_RADIUS_M
            return distance_km(zone.latitude, zone.longitude, point.latitude, point.longitude) * 1000 <= radius

        return ok([{
            **_zone(zone),
            "city": zone.city,
            "points": [
                {
                    "id": str(p.pk), "name": p.name, "category": p.category, "is_official": p.is_official,
                    "latitude": float(p.latitude), "longitude": float(p.longitude),
                }
                for p in points if inside(zone, p)
            ],
        } for zone in zones])


_Q = Q
