from decimal import Decimal

from django.utils import timezone
from rest_framework import serializers

from apps.events.models.EventModel import Event
from apps.journeys import planner
from apps.journeys.models import (
    JourneyChecklistItem,
    JourneyDay,
    JourneyItem,
    JourneyPlan,
    JourneyReference,
)
from apps.temples.models import Temple

MAX_NOTES = 4000
MAX_BUDGET = Decimal("10000000")


class JourneyItemSerializer(serializers.ModelSerializer):
    temple = serializers.PrimaryKeyRelatedField(
        queryset=Temple.objects.filter(is_active=True, del_flag=0), required=False, allow_null=True,
    )
    event = serializers.PrimaryKeyRelatedField(
        queryset=Event.objects.filter(del_flag=0), required=False, allow_null=True,
    )
    temple_name = serializers.CharField(source="temple.name", read_only=True, default=None)
    event_name = serializers.CharField(source="event.event_name", read_only=True, default=None)
    event_date = serializers.DateField(source="event.event_date", read_only=True, default=None)

    class Meta:
        model = JourneyItem
        fields = [
            "id", "position", "period", "kind", "title", "details", "temple", "temple_name",
            "event", "event_name", "event_date", "source", "is_edited", "is_done",
        ]
        read_only_fields = ["id", "position", "source", "is_edited"]

    def validate_title(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Title can't be empty.")
        return value

    def validate_details(self, value):
        if len(value) > 1000:
            raise serializers.ValidationError("Keep details under 1000 characters.")
        return value.strip()


class JourneyDaySerializer(serializers.ModelSerializer):
    items = JourneyItemSerializer(many=True, read_only=True)

    class Meta:
        model = JourneyDay
        fields = ["day_number", "date", "title", "items"]


class JourneyChecklistItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = JourneyChecklistItem
        fields = ["id", "text", "category", "is_done", "position", "source"]
        read_only_fields = ["id", "position", "source"]

    def validate_text(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Text can't be empty.")
        return value


class JourneyReferenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = JourneyReference
        fields = [
            "id", "kind", "title", "provider", "booking_reference", "url",
            "start_date", "end_date", "notes",
        ]
        read_only_fields = ["id"]

    def validate_url(self, value):
        if value and not value.lower().startswith("https://"):
            raise serializers.ValidationError("Use an https:// link.")
        return value

    def validate(self, attrs):
        start = attrs.get("start_date", getattr(self.instance, "start_date", None))
        end = attrs.get("end_date", getattr(self.instance, "end_date", None))
        if start and end and end < start:
            raise serializers.ValidationError({"end_date": "End date must be on or after the start date."})
        return attrs


class JourneyPlanInputMixin:
    """Validation shared by create and update."""

    def validate_title(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Give the journey a name.")
        return value

    def validate_interests(self, value):
        if not isinstance(value, list):
            raise serializers.ValidationError("Interests must be a list.")
        unknown = [v for v in value if v not in JourneyPlan.INTERESTS]
        if unknown:
            raise serializers.ValidationError(f"Unknown interests: {', '.join(map(str, unknown))}.")
        return list(dict.fromkeys(value))

    def validate_budget_amount(self, value):
        if value is not None and (value < 0 or value > MAX_BUDGET):
            raise serializers.ValidationError("Enter a budget between 0 and 1,00,00,000.")
        return value

    def validate_notes(self, value):
        if len(value) > MAX_NOTES:
            raise serializers.ValidationError(f"Keep notes under {MAX_NOTES} characters.")
        return value

    def validate_language(self, value):
        if value not in planner.LANGUAGES:
            raise serializers.ValidationError("Language must be en, hi or mr.")
        return value

    def validate(self, attrs):
        def current(name):
            if name in attrs:
                return attrs[name]
            if self.instance is not None:
                return getattr(self.instance, name)
            # Creating: an omitted field takes the model default.
            return JourneyPlan._meta.get_field(name).get_default()

        arrival, departure = current("arrival_date"), current("departure_date")
        if bool(arrival) != bool(departure):
            raise serializers.ValidationError(
                {"departure_date": "Choose both the arrival and departure dates, or neither."}
            )
        if arrival and departure:
            if departure < arrival:
                raise serializers.ValidationError(
                    {"departure_date": "Departure must be on or after arrival."}
                )
            if (departure - arrival).days + 1 > JourneyPlan.MAX_DAYS:
                raise serializers.ValidationError(
                    {"departure_date": f"Plan up to {JourneyPlan.MAX_DAYS} days at a time."}
                )
            changed = "arrival_date" in attrs and (
                self.instance is None or attrs["arrival_date"] != self.instance.arrival_date
            )
            completed = current("status") == JourneyPlan.Status.COMPLETED
            if changed and not completed and arrival < timezone.localdate():
                raise serializers.ValidationError({"arrival_date": "Arrival can't be in the past."})

        duration = current("duration_days")
        if duration is not None and not 1 <= duration <= JourneyPlan.MAX_DAYS:
            raise serializers.ValidationError(
                {"duration_days": f"Choose between 1 and {JourneyPlan.MAX_DAYS} days."}
            )

        adults, children, seniors = (current(n) or 0 for n in ("adults", "children", "seniors"))
        if adults < 1:
            raise serializers.ValidationError({"adults": "At least one adult must travel."})
        if adults + children + seniors > JourneyPlan.MAX_TRAVELLERS:
            raise serializers.ValidationError(
                {"adults": f"Plan for up to {JourneyPlan.MAX_TRAVELLERS} travellers."}
            )
        return attrs


class JourneyPlanSummarySerializer(serializers.ModelSerializer):
    travellers = serializers.IntegerField(read_only=True)
    day_count = serializers.SerializerMethodField()
    checklist_done = serializers.IntegerField(read_only=True, default=0)
    checklist_total = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = JourneyPlan
        fields = [
            "id", "title", "status", "origin_city", "origin_state", "arrival_date",
            "departure_date", "duration_days", "travellers", "day_count",
            "checklist_done", "checklist_total", "itinerary_generated_at",
            "created_at", "updated_at",
        ]

    def get_day_count(self, plan):
        return planner.day_count(plan)


class JourneyPlanSerializer(JourneyPlanInputMixin, serializers.ModelSerializer):
    travellers = serializers.IntegerField(read_only=True)
    day_count = serializers.SerializerMethodField()
    recommended_days = serializers.SerializerMethodField()
    budget_plan = serializers.SerializerMethodField()
    days = JourneyDaySerializer(many=True, read_only=True)
    checklist = JourneyChecklistItemSerializer(many=True, read_only=True)
    references = JourneyReferenceSerializer(many=True, read_only=True)

    class Meta:
        model = JourneyPlan
        fields = [
            "id", "title", "status", "origin_city", "origin_state", "arrival_date",
            "departure_date", "duration_days", "date_flexibility", "adults", "children",
            "seniors", "travellers", "needs_accessibility", "accessibility_notes",
            "transport_mode", "budget_amount", "budget_basis", "accommodation_preference",
            "interests", "dietary_notes", "notes", "language", "day_count",
            "recommended_days", "budget_plan", "itinerary_generated_at", "days",
            "checklist", "references", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "itinerary_generated_at", "created_at", "updated_at"]

    def get_day_count(self, plan):
        return planner.day_count(plan)

    def get_recommended_days(self, plan):
        return planner.recommended_days(plan)

    def get_budget_plan(self, plan):
        return planner.budget_plan(plan)
