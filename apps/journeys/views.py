"""
Plan Your Kumbh Journey API (all under /api/journeys/, JWT required).

Every lookup is scoped to request.user: another user's journey, day, item,
checklist entry or reference answers 404, the same as one that doesn't
exist. Responses follow the project's {"status", "data"} / {"status",
"errors"} convention.
"""

from django.db import transaction
from django.db.models import Count, Max, Q
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication

from apps.journeys import guide, planner
from apps.journeys.export import itinerary_text
from apps.journeys.models import (
    JourneyChecklistItem,
    JourneyDay,
    JourneyItem,
    JourneyPlan,
    JourneyReference,
)
from apps.journeys.serializers import (
    JourneyChecklistItemSerializer,
    JourneyItemSerializer,
    JourneyPlanSerializer,
    JourneyPlanSummarySerializer,
    JourneyReferenceSerializer,
)

_ORDERINGS = {
    "arrival": ["arrival_date", "-updated_at"],
    "-arrival": ["-arrival_date", "-updated_at"],
    "-updated": ["-updated_at"],
    "-created": ["-created_at"],
}


def ok(data, code=status.HTTP_200_OK):
    return Response({"status": "success", "data": data}, status=code)


def error(errors, code=status.HTTP_400_BAD_REQUEST):
    return Response({"status": "error", "errors": errors}, status=code)


class JourneyPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = "page_size"
    max_page_size = 50


class _Authenticated(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def journey(self, request, journey_id, *, lock=False):
        queryset = JourneyPlan.objects.filter(user=request.user)
        if lock:
            queryset = queryset.select_for_update()
        return get_object_or_404(queryset, pk=journey_id)

    def detail(self, request, plan, code=status.HTTP_200_OK, extra=None):
        plan = (
            JourneyPlan.objects.filter(pk=plan.pk, user=request.user)
            .prefetch_related(
                "days__items__temple", "days__items__event", "checklist", "references",
            )
            .get()
        )
        data = JourneyPlanSerializer(plan).data
        if extra:
            data = {**data, **extra}
        return ok(data, code)


class JourneyListCreateAPI(_Authenticated):
    """GET: the user's journeys (paginated; ?status=, ?ordering=).
    POST: create (optionally ?generate=true to build suggestions)."""

    def get(self, request):
        queryset = JourneyPlan.objects.filter(user=request.user).annotate(
            checklist_total=Count("checklist", distinct=True),
            checklist_done=Count("checklist", filter=Q(checklist__is_done=True), distinct=True),
        )
        wanted = request.query_params.get("status")
        if wanted:
            statuses = [s for s in wanted.split(",") if s in JourneyPlan.Status.values]
            if not statuses:
                return error({"status": "Unknown status filter."})
            queryset = queryset.filter(status__in=statuses)
        queryset = queryset.order_by(*_ORDERINGS.get(request.query_params.get("ordering"), ["-updated_at"]))

        paginator = JourneyPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        return ok({
            "count": paginator.page.paginator.count,
            "page": paginator.page.number,
            "num_pages": paginator.page.paginator.num_pages,
            "has_next": paginator.page.has_next(),
            "results": JourneyPlanSummarySerializer(page, many=True).data,
        })

    def post(self, request):
        if JourneyPlan.objects.filter(user=request.user).count() >= JourneyPlan.MAX_PLANS_PER_USER:
            return error({"non_field_errors": [
                f"You can keep up to {JourneyPlan.MAX_PLANS_PER_USER} journeys. Delete one to add another."
            ]})
        serializer = JourneyPlanSerializer(data=request.data)
        if not serializer.is_valid():
            return error(serializer.errors)
        plan = serializer.save(user=request.user)
        extra = None
        if request.query_params.get("generate") in ("1", "true"):
            extra = {"generated": planner.generate(plan)}
        return self.detail(request, plan, status.HTTP_201_CREATED, extra)


class JourneyDetailAPI(_Authenticated):
    def get(self, request, journey_id):
        return self.detail(request, self.journey(request, journey_id))

    def patch(self, request, journey_id):
        plan = self.journey(request, journey_id)
        serializer = JourneyPlanSerializer(plan, data=request.data, partial=True)
        if not serializer.is_valid():
            return error(serializer.errors)
        serializer.save()
        return self.detail(request, plan)

    def delete(self, request, journey_id):
        self.journey(request, journey_id).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class JourneyGenerateAPI(_Authenticated):
    """Build or rebuild suggestions; the user's own items and edits stay."""

    def post(self, request, journey_id):
        plan = self.journey(request, journey_id)
        language = request.data.get("language")
        if language in planner.LANGUAGES and language != plan.language:
            plan.language = language
            plan.save(update_fields=["language", "updated_at"])
        stats = planner.generate(plan)
        return self.detail(request, plan, extra={"generated": stats})


class JourneyDuplicateAPI(_Authenticated):
    """Copy a plan with its itinerary and checklist (unticked). Booking
    references are not copied: they belong to the original trip."""

    @transaction.atomic
    def post(self, request, journey_id):
        if JourneyPlan.objects.filter(user=request.user).count() >= JourneyPlan.MAX_PLANS_PER_USER:
            return error({"non_field_errors": [
                f"You can keep up to {JourneyPlan.MAX_PLANS_PER_USER} journeys."
            ]})
        source = self.journey(request, journey_id)
        days = list(source.days.prefetch_related("items"))
        checklist = list(source.checklist.all())

        copy = JourneyPlan.objects.get(pk=source.pk)
        copy.pk = None
        copy.id = None
        copy._state.adding = True
        copy.title = f"{source.title} (copy)"[:120]
        copy.status = JourneyPlan.Status.DRAFT
        copy.save()
        for day in days:
            new_day = JourneyDay.objects.create(
                journey=copy, day_number=day.day_number, date=day.date, title=day.title,
            )
            JourneyItem.objects.bulk_create([
                JourneyItem(
                    day=new_day, position=i.position, period=i.period, kind=i.kind,
                    title=i.title, details=i.details, temple_id=i.temple_id,
                    event_id=i.event_id, source=i.source, is_edited=i.is_edited,
                )
                for i in day.items.all()
            ])
        JourneyChecklistItem.objects.bulk_create([
            JourneyChecklistItem(
                journey=copy, text=c.text, category=c.category, position=c.position, source=c.source,
            )
            for c in checklist
        ])
        return self.detail(request, copy, status.HTTP_201_CREATED)


class JourneyItemsAPI(_Authenticated):
    """POST: add an item to a day ({"day_number": 2, "title": ...})."""

    def post(self, request, journey_id):
        plan = self.journey(request, journey_id)
        try:
            day_number = int(request.data.get("day_number"))
        except (TypeError, ValueError):
            return error({"day_number": "Choose a day."})
        day = plan.days.filter(day_number=day_number).first()
        if day is None:
            return error({"day_number": "That day isn't in this journey."})
        if day.items.count() >= JourneyItem.MAX_PER_DAY:
            return error({"non_field_errors": [f"Up to {JourneyItem.MAX_PER_DAY} items per day."]})
        serializer = JourneyItemSerializer(data=request.data)
        if not serializer.is_valid():
            return error(serializer.errors)
        position = (day.items.aggregate(m=Max("position"))["m"] or 0) + 1
        item = serializer.save(day=day, position=position, source=JourneyItem.Source.USER)
        return ok(JourneyItemSerializer(item).data, status.HTTP_201_CREATED)


class JourneyItemDetailAPI(_Authenticated):
    _EDIT_FIELDS = {"title", "details", "period", "kind", "temple", "event"}

    def item(self, request, journey_id, item_id):
        plan = self.journey(request, journey_id)
        return plan, get_object_or_404(JourneyItem, pk=item_id, day__journey=plan)

    def patch(self, request, journey_id, item_id):
        plan, item = self.item(request, journey_id, item_id)
        serializer = JourneyItemSerializer(item, data=request.data, partial=True)
        if not serializer.is_valid():
            return error(serializer.errors)
        extra = {}
        if "day_number" in request.data:
            try:
                target = plan.days.get(day_number=int(request.data["day_number"]))
            except (JourneyDay.DoesNotExist, TypeError, ValueError):
                return error({"day_number": "That day isn't in this journey."})
            if target.pk != item.day_id:
                extra = {
                    "day": target,
                    "position": (target.items.aggregate(m=Max("position"))["m"] or 0) + 1,
                }
        edited = bool(self._EDIT_FIELDS & set(request.data)) or bool(extra)
        if edited and item.source == JourneyItem.Source.SUGGESTED:
            extra["is_edited"] = True
        item = serializer.save(**extra)
        return ok(JourneyItemSerializer(item).data)

    def delete(self, request, journey_id, item_id):
        _, item = self.item(request, journey_id, item_id)
        item.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class JourneyDayReorderAPI(_Authenticated):
    """POST {"item_ids": [...]} — the day's items in their new order."""

    @transaction.atomic
    def post(self, request, journey_id, day_number):
        plan = self.journey(request, journey_id)
        day = get_object_or_404(JourneyDay, journey=plan, day_number=day_number)
        ids = request.data.get("item_ids")
        current = list(day.items.values_list("id", flat=True))
        if (
            not isinstance(ids, list)
            or len(ids) != len(current)
            or {str(i) for i in ids} != {str(i) for i in current}
        ):
            return error({"item_ids": "Send every item of this day exactly once."})
        items = {str(i.pk): i for i in day.items.all()}
        for position, item_id in enumerate(ids):
            item = items[str(item_id)]
            item.position = position
            if item.source == JourneyItem.Source.SUGGESTED:
                item.is_edited = True
        JourneyItem.objects.bulk_update(items.values(), ["position", "is_edited"])
        return ok(JourneyItemSerializer(day.items.all().order_by("position"), many=True).data)


class JourneyChecklistAPI(_Authenticated):
    def post(self, request, journey_id):
        plan = self.journey(request, journey_id)
        if plan.checklist.count() >= JourneyChecklistItem.MAX_ITEMS:
            return error({"non_field_errors": [f"Up to {JourneyChecklistItem.MAX_ITEMS} checklist items."]})
        serializer = JourneyChecklistItemSerializer(data=request.data)
        if not serializer.is_valid():
            return error(serializer.errors)
        position = (plan.checklist.aggregate(m=Max("position"))["m"] or 0) + 1
        item = serializer.save(journey=plan, position=position, source=JourneyItem.Source.USER)
        return ok(JourneyChecklistItemSerializer(item).data, status.HTTP_201_CREATED)


class JourneyChecklistDetailAPI(_Authenticated):
    def entry(self, request, journey_id, item_id):
        plan = self.journey(request, journey_id)
        return get_object_or_404(JourneyChecklistItem, pk=item_id, journey=plan)

    def patch(self, request, journey_id, item_id):
        item = self.entry(request, journey_id, item_id)
        serializer = JourneyChecklistItemSerializer(item, data=request.data, partial=True)
        if not serializer.is_valid():
            return error(serializer.errors)
        return ok(JourneyChecklistItemSerializer(serializer.save()).data)

    def delete(self, request, journey_id, item_id):
        self.entry(request, journey_id, item_id).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class JourneyReferencesAPI(_Authenticated):
    def post(self, request, journey_id):
        plan = self.journey(request, journey_id)
        if plan.references.count() >= JourneyReference.MAX_PER_JOURNEY:
            return error({"non_field_errors": [f"Up to {JourneyReference.MAX_PER_JOURNEY} entries."]})
        serializer = JourneyReferenceSerializer(data=request.data)
        if not serializer.is_valid():
            return error(serializer.errors)
        return ok(JourneyReferenceSerializer(serializer.save(journey=plan)).data, status.HTTP_201_CREATED)


class JourneyReferenceDetailAPI(_Authenticated):
    def entry(self, request, journey_id, reference_id):
        plan = self.journey(request, journey_id)
        return get_object_or_404(JourneyReference, pk=reference_id, journey=plan)

    def patch(self, request, journey_id, reference_id):
        reference = self.entry(request, journey_id, reference_id)
        serializer = JourneyReferenceSerializer(reference, data=request.data, partial=True)
        if not serializer.is_valid():
            return error(serializer.errors)
        return ok(JourneyReferenceSerializer(serializer.save()).data)

    def delete(self, request, journey_id, reference_id):
        self.entry(request, journey_id, reference_id).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class JourneyExportAPI(_Authenticated):
    """Plain-text itinerary for sharing (WhatsApp, SMS, notes)."""

    def get(self, request, journey_id):
        plan = (
            JourneyPlan.objects.filter(pk=journey_id, user=request.user)
            .prefetch_related("days__items", "checklist", "references")
            .first()
        )
        if plan is None:
            return error({"detail": "Not found."}, status.HTTP_404_NOT_FOUND)
        return ok({"text": itinerary_text(plan)})


class JourneyGuideAPI(_Authenticated):
    """Verified links, transport and stay guidance, contacts and important
    dates (from the events database), with sources and check dates."""

    def get(self, request):
        language = request.query_params.get("language", "en")
        if language not in planner.LANGUAGES:
            language = "en"
        return ok(guide.planning_guide(language))
