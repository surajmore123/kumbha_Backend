"""
Reunification API (all under /api/reunification/, JWT required). Positions are
never copied here: the app reads them from `/api/location/`, and a route is only
built after the same consent checks. Coordinates are never logged or audited.
"""

from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers as drf, status
from rest_framework.throttling import UserRateThrottle

from apps.family.models import FamilyMember
from apps.family.views import error, forbidden, ok
from apps.familylocation import policy as location_policy
from apps.familylocation import services as location_services
from apps.familylocation.models import LocationSession
from apps.lostfound import policy as case_policy
from apps.lostfound.models import LostFoundCase
from apps.lostfound.serializers import FamilyCaseSerializer
from apps.lostfound.services import add_note
from apps.reunification import policy, routing, services
from apps.reunification.models import MeetingPoint
from apps.reunification.services import ReunionError
from apps.safety.views import _Safety


class RouteThrottle(UserRateThrottle):
    scope = "reunion_route"
    rate = "60/hour"


class NotifyThrottle(UserRateThrottle):
    scope = "reunion_notify"
    rate = "10/hour"


class _Position(drf.Serializer):
    latitude = drf.FloatField(min_value=-90, max_value=90)
    longitude = drf.FloatField(min_value=-180, max_value=180)


class PointInput(_Position):
    name = drf.CharField(max_length=160)
    description = drf.CharField(max_length=500, required=False, allow_blank=True)


class GuidanceInput(drf.Serializer):
    origin = _Position(required=False, allow_null=True)


class RouteInput(drf.Serializer):
    origin = _Position()
    kind = drf.ChoiceField(choices=["point", "member"])
    target_id = drf.UUIDField()
    case_id = drf.UUIDField(required=False, allow_null=True)


class NotifyInput(drf.Serializer):
    kind = drf.ChoiceField(choices=["check_map", "meet_at_point"])
    point_id = drf.UUIDField(required=False, allow_null=True)


class CoordinationInput(drf.Serializer):
    event = drf.ChoiceField(choices=["family_arrived", "person_arrived"], required=False)
    update = drf.CharField(max_length=1000, required=False, allow_blank=True)


def point_body(point):
    return {
        "id": str(point.pk),
        "name": point.name,
        "description": point.description,
        "category": point.category,
        "status": point.status,
        "is_verified": point.status == MeetingPoint.Status.VERIFIED,
        "is_official": point.is_official,
        "source_type": point.source_type,
        "source_detail": point.source_detail if point.status == MeetingPoint.Status.VERIFIED else "",
        "is_private": point.family_id is not None,
        "family_id": str(point.family_id) if point.family_id else None,
        "latitude": float(point.latitude),
        "longitude": float(point.longitude),
        "address": point.address,
        "opening_hours": point.opening_hours,
        "contact_phone": point.contact_phone,
        "verified_at": point.verified_at,
    }


def plan_body(case, plan):
    point = plan.meeting_point if plan else None
    return {
        "stage": services.stage_of(case, plan),
        "meeting_point": point_body(point) if point else None,
        "selected_at": plan.selected_at if plan else None,
        "family_arrived_at": plan.family_arrived_at if plan else None,
        "person_arrived_at": plan.person_arrived_at if plan else None,
    }


def case_marker(request, case):
    """What the map shows for a case: only places this person may see."""
    full = FamilyCaseSerializer(case, context={"request": request}).data
    return {
        "id": str(case.pk),
        "reference": case.reference,
        "status": case.status,
        "person_name": case.person_name or (case.member.display_name if case.member_id else ""),
        "member_id": str(case.member_id) if case.member_id else None,
        "protected": policy.is_protected(case),
        "event_at": full["event_at"],
        "location_text": full["location_text"],
        "latitude": full["latitude"],
        "longitude": full["longitude"],
        "sightings": full["sightings"],
        "plan": plan_body(case, services.plan_for(case)),
    }


class _Reunion(_Safety):
    def case_for(self, request, case_id):
        """The case, or 404 for anyone who can't coordinate it."""
        case = get_object_or_404(LostFoundCase.objects.select_related("member__user", "family"), pk=case_id)
        return case if policy.can_coordinate(request.user, case) else None

    def nothing(self):
        return error({"detail": "Not found."}, status.HTTP_404_NOT_FOUND)

    def refused(self, problem):
        body = {problem.field: [problem.message]}
        if problem.code:
            body["code"] = problem.code
        return error(body, status.HTTP_409_CONFLICT)


class OverviewAPI(_Reunion):
    def get(self, request):
        """The person's open cases and whether they themselves need the
        protected guidance. Positions come from the location feed."""
        family_id = request.query_params.get("family_id")
        actor = self.actor_for(request, family_id) if family_id else None
        response = ok({
            "cases": [case_marker(request, c) for c in policy.family_side_cases(request.user)],
            "self_protected": policy.self_protected(request.user, actor),
        })
        response["Cache-Control"] = "no-store"
        return response


class PointListAPI(_Reunion):
    PAGE_SIZE = 100

    def get(self, request):
        points = policy.visible_points(request.user)
        category = request.query_params.get("category")
        if category:
            if category not in MeetingPoint.Category.values:
                return error({"category": ["Unknown category."]})
            points = points.filter(category=category)
        if request.query_params.get("verified") == "true":
            points = points.filter(status=MeetingPoint.Status.VERIFIED)
        page = Paginator(points.order_by("name", "id"), self.PAGE_SIZE).get_page(request.query_params.get("page"))
        return ok({
            "results": [point_body(p) for p in page],
            "count": page.paginator.count,
            "has_next": page.has_next(),
        })


class FamilyPointListAPI(_Reunion):
    def post(self, request, family_id):
        actor = self.actor_for(request, family_id)
        serializer = PointInput(data=request.data)
        if not serializer.is_valid():
            return error(serializer.errors)
        return ok(point_body(services.create_family_point(actor, serializer.validated_data)), status.HTTP_201_CREATED)


class _FamilyPoint(_Reunion):
    def editable(self, request, point_id):
        point = get_object_or_404(policy.visible_points(request.user), pk=point_id)
        actor = FamilyMember.objects.filter(family_id=point.family_id, user=request.user).first()
        if actor is None or not policy.can_edit_point(actor, point):
            return None, None
        return point, actor


class FamilyPointDetailAPI(_FamilyPoint):
    def delete(self, request, point_id):
        point, actor = self.editable(request, point_id)
        if point is None:
            return forbidden()
        point.status = MeetingPoint.Status.RETIRED
        point.save(update_fields=["status", "updated_at"])
        return ok({"removed": True})


class FamilyPointSuggestAPI(_FamilyPoint):
    def post(self, request, point_id):
        point, actor = self.editable(request, point_id)
        if point is None:
            return forbidden()
        return ok(point_body(services.suggest_point(actor, point)))


class CaseDetailAPI(_Reunion):
    def get(self, request, case_id):
        case = self.case_for(request, case_id)
        if case is None:
            return self.nothing()
        body = FamilyCaseSerializer(case, context={"request": request}).data
        response = ok({
            "case": body,
            "plan": plan_body(case, services.plan_for(case)),
            "protected": policy.is_protected(case),
            "can_operate": case_policy.can_operate(request.user, case),
        })
        response["Cache-Control"] = "no-store"
        return response


class CaseGuidanceAPI(_Reunion):
    """The origin is in the body, so it's never in a URL or an access log."""

    def post(self, request, case_id):
        case = self.case_for(request, case_id)
        if case is None:
            return self.nothing()
        serializer = GuidanceInput(data=request.data)
        if not serializer.is_valid():
            return error(serializer.errors)
        origin = serializer.validated_data.get("origin")
        place = (origin["latitude"], origin["longitude"]) if origin else None
        return ok({
            "protected": policy.is_protected(case),
            "points": [
                {**point_body(point), "straight_line_km": None if km is None else round(km, 2)}
                for point, km in services.recommended(case, place)
            ],
        })


class CaseMeetingPointAPI(_Reunion):
    def post(self, request, case_id):
        case = self.case_for(request, case_id)
        if case is None:
            return self.nothing()
        point_id = request.data.get("meeting_point_id")
        try:
            point = policy.visible_points(request.user).filter(pk=point_id).first()
        except (ValidationError, ValueError, TypeError):
            point = None
        if point is None:
            return error({"meeting_point_id": ["Choose a meeting point."]})
        try:
            plan = services.choose_point(case, point, request.user)
        except ReunionError as problem:
            return self.refused(problem)
        return ok(plan_body(case, plan))


class CaseCoordinationAPI(_Reunion):
    """Staff record arrivals and approved updates. Family can only say they've
    arrived. Neither changes the case's status."""

    def post(self, request, case_id):
        case = self.case_for(request, case_id)
        if case is None:
            return self.nothing()
        serializer = CoordinationInput(data=request.data)
        if not serializer.is_valid():
            return error(serializer.errors)
        data = serializer.validated_data
        operator = case_policy.can_operate(request.user, case)
        event = data.get("event")
        update = data.get("update", "").strip()
        if not operator and (update or event != "family_arrived"):
            return forbidden()
        try:
            if event:
                services.mark_arrived(case, request.user, event.split("_")[0])
        except ReunionError as problem:
            return self.refused(problem)
        if update:
            add_note(case, request.user, "family_update", update)
        return ok(plan_body(case, services.plan_for(case)))


class RouteAPI(_Reunion):
    """A walking route to a place this person may reach. The destination is
    looked up here, so a route can't be used to learn anyone's position."""

    throttle_classes = [RouteThrottle]

    def member_target(self, request, member_id):
        member = get_object_or_404(FamilyMember.objects.select_related("user", "family"), pk=member_id)
        actor = member.family.members.filter(user=request.user).first()
        if actor is None:
            return None
        session = LocationSession.objects.filter(
            member=member, status__in=LocationSession.OPEN,
        ).select_related("location", "member__user").first()
        if session is not None:
            session = location_services.settle(session)
        if session is None or session.status != LocationSession.Status.ACTIVE:
            return None
        location = getattr(session, "location", None)
        if location is None or not location_policy.can_view(actor, session):
            return None
        return {"actor": actor, "member": member, "location": location}

    def post(self, request):
        if self._insecure:
            return self.handle_insecure()
        serializer = RouteInput(data=request.data)
        if not serializer.is_valid():
            return error(serializer.errors)
        data = serializer.validated_data
        case = None
        if data.get("case_id"):
            case = self.case_for(request, data["case_id"])
            if case is None:
                return self.nothing()
        body = {"caution": None}
        if data["kind"] == "point":
            point = get_object_or_404(policy.visible_points(request.user), pk=data["target_id"])
            if case is not None and not policy.is_safe_point(case, point):
                return self.refused(ReunionError("This person needs a verified, staffed help point.", code="use_safe_point"))
            destination = (point.latitude, point.longitude)
            body.update(name=point.name, state=None, captured_at=None)
        else:
            target = self.member_target(request, data["target_id"])
            if target is None:
                return self.nothing()
            if policy.self_protected(request.user, target["actor"]):
                return self.refused(ReunionError("Go to a help point and stay with staff.", code="use_safe_point"))
            location = target["location"]
            destination = (location.latitude, location.longitude)
            body.update(
                name=target["member"].display_name,
                state=location_services.freshness(location),
                captured_at=location.captured_at,
            )
            if policy.open_protected_case(target["member"]) is not None:
                body["caution"] = "stay_put"
        origin = (data["origin"]["latitude"], data["origin"]["longitude"])
        try:
            route = routing.walking_route(origin, destination)
        except routing.RoutingUnavailable:
            return error(
                {"detail": "Routes aren't available right now.", "code": "routing_unavailable"},
                status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        response = ok({**body, **route, "provider": "google", "fetched_at": timezone.now()})
        response["Cache-Control"] = "no-store"
        return response


class NotifyFamilyAPI(_Reunion):
    throttle_classes = [NotifyThrottle]

    def post(self, request, family_id):
        actor = self.actor_for(request, family_id)
        serializer = NotifyInput(data=request.data)
        if not serializer.is_valid():
            return error(serializer.errors)
        data = serializer.validated_data
        point = None
        if data.get("point_id"):
            point = policy.visible_points(request.user).filter(pk=data["point_id"]).first()
            if point is None or (point.family_id and point.family_id != actor.family_id):
                return error({"point_id": ["Choose a meeting point."]})
        return ok({"people": services.notify_family(actor, data["kind"], point)})

