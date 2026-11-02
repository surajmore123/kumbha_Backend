"""
Plan Your Kumbh Journey: a pilgrim's own trip plan.

A plan belongs to one user (ownership comes from the authenticated
request, never from the request body). Temples and events are linked by
foreign key, not copied. Nothing here is a booking: transport and stay
details are references the user typed in.

Only what the plan needs is stored: traveller counts (no names or IDs),
a manually entered origin town (no GPS), and optional accessibility and
dietary notes.
"""

import uuid

from django.conf import settings
from django.db import models
from django.db.models import F, Q


class JourneyPlan(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PLANNED = "planned", "Planned"
        COMPLETED = "completed", "Completed"

    class Flexibility(models.TextChoices):
        FIXED = "fixed", "Fixed dates"
        FLEXIBLE = "flexible", "Flexible by a few days"

    class Transport(models.TextChoices):
        TRAIN = "train", "Train"
        BUS = "bus", "Bus"
        FLIGHT = "flight", "Flight"
        PRIVATE = "private", "Private vehicle"
        UNDECIDED = "undecided", "Not decided"

    class BudgetBasis(models.TextChoices):
        TOTAL = "total", "Total for the group"
        PER_PERSON = "per_person", "Per person"

    class Stay(models.TextChoices):
        HOTEL = "hotel", "Hotel"
        DHARAMSHALA = "dharamshala", "Dharamshala"
        ASHRAM = "ashram", "Ashram"
        BUDGET = "budget", "Budget stay"
        FAMILY = "family", "Family accommodation"
        UNDECIDED = "undecided", "Not decided"

    INTERESTS = ("bathing", "temples", "learning", "akhadas", "sightseeing")

    MAX_DAYS = 15
    MAX_TRAVELLERS = 50
    MAX_PLANS_PER_USER = 20

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="journeys",
    )
    title = models.CharField(max_length=120)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)

    origin_city = models.CharField(max_length=100, blank=True)
    origin_state = models.CharField(max_length=100, blank=True)

    arrival_date = models.DateField(null=True, blank=True)
    departure_date = models.DateField(null=True, blank=True)
    # Used when dates aren't chosen yet.
    duration_days = models.PositiveSmallIntegerField(null=True, blank=True)
    date_flexibility = models.CharField(
        max_length=10, choices=Flexibility.choices, default=Flexibility.FIXED,
    )

    adults = models.PositiveSmallIntegerField(default=1)
    children = models.PositiveSmallIntegerField(default=0)
    seniors = models.PositiveSmallIntegerField(default=0)
    needs_accessibility = models.BooleanField(default=False)
    accessibility_notes = models.CharField(max_length=300, blank=True)

    transport_mode = models.CharField(
        max_length=10, choices=Transport.choices, default=Transport.UNDECIDED,
    )
    budget_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    budget_basis = models.CharField(
        max_length=10, choices=BudgetBasis.choices, default=BudgetBasis.TOTAL,
    )
    accommodation_preference = models.CharField(
        max_length=12, choices=Stay.choices, default=Stay.UNDECIDED,
    )
    interests = models.JSONField(default=list, blank=True)
    dietary_notes = models.CharField(max_length=200, blank=True)
    notes = models.TextField(blank=True)
    # Language the suggestions were written in (en / hi / mr).
    language = models.CharField(max_length=2, default="en")

    itinerary_generated_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "journey_plans"
        ordering = ["-updated_at"]
        indexes = [
            models.Index(fields=["user", "status"]),
            models.Index(fields=["user", "arrival_date"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(arrival_date__isnull=True)
                | Q(departure_date__isnull=True)
                | Q(departure_date__gte=F("arrival_date")),
                name="journey_departure_after_arrival",
            ),
            models.CheckConstraint(condition=Q(adults__gte=1), name="journey_at_least_one_adult"),
            models.CheckConstraint(
                condition=Q(budget_amount__isnull=True) | Q(budget_amount__gte=0),
                name="journey_budget_not_negative",
            ),
        ]

    def __str__(self):
        return f"{self.title} ({self.user_id})"

    @property
    def travellers(self) -> int:
        return self.adults + self.children + self.seniors


class JourneyDay(models.Model):
    journey = models.ForeignKey(JourneyPlan, on_delete=models.CASCADE, related_name="days")
    day_number = models.PositiveSmallIntegerField()
    date = models.DateField(null=True, blank=True)
    title = models.CharField(max_length=120, blank=True)

    class Meta:
        db_table = "journey_days"
        ordering = ["day_number"]
        constraints = [
            models.UniqueConstraint(fields=["journey", "day_number"], name="journey_day_unique"),
        ]

    def __str__(self):
        return f"{self.journey_id} day {self.day_number}"


class JourneyItem(models.Model):
    class Period(models.TextChoices):
        EARLY_MORNING = "early_morning", "Early morning"
        MORNING = "morning", "Morning"
        AFTERNOON = "afternoon", "Afternoon"
        EVENING = "evening", "Evening"
        NIGHT = "night", "Night"
        ANYTIME = "anytime", "Any time"

    class Kind(models.TextChoices):
        TRAVEL = "travel", "Travel"
        TEMPLE = "temple", "Temple"
        GHAT = "ghat", "Ghat"
        BATHING = "bathing", "Sacred bath"
        EVENT = "event", "Event"
        REST = "rest", "Rest"
        MEAL = "meal", "Meal"
        AKHADA = "akhada", "Akhada"
        SIGHTSEEING = "sightseeing", "Sightseeing"
        NOTE = "note", "Note"

    class Source(models.TextChoices):
        SUGGESTED = "suggested", "Suggested"
        USER = "user", "Added by user"

    MAX_PER_DAY = 40

    day = models.ForeignKey(JourneyDay, on_delete=models.CASCADE, related_name="items")
    position = models.PositiveSmallIntegerField(default=0)
    period = models.CharField(max_length=14, choices=Period.choices, default=Period.ANYTIME)
    kind = models.CharField(max_length=12, choices=Kind.choices, default=Kind.NOTE)
    title = models.CharField(max_length=150)
    details = models.TextField(blank=True)
    temple = models.ForeignKey(
        "temples.Temple", on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )
    event = models.ForeignKey(
        "events.Event", on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )
    source = models.CharField(max_length=10, choices=Source.choices, default=Source.USER)
    # A suggestion the user changed; regenerating keeps it.
    is_edited = models.BooleanField(default=False)
    is_done = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "journey_items"
        ordering = ["position", "id"]
        indexes = [models.Index(fields=["day", "position"])]

    def __str__(self):
        return self.title


class JourneyChecklistItem(models.Model):
    class Category(models.TextChoices):
        DOCUMENTS = "documents", "Documents"
        HEALTH = "health", "Health"
        PACKING = "packing", "Packing"
        TRAVEL = "travel", "Travel"
        FAMILY = "family", "Family & safety"
        OTHER = "other", "Other"

    MAX_ITEMS = 100

    journey = models.ForeignKey(JourneyPlan, on_delete=models.CASCADE, related_name="checklist")
    text = models.CharField(max_length=200)
    category = models.CharField(max_length=10, choices=Category.choices, default=Category.OTHER)
    is_done = models.BooleanField(default=False)
    position = models.PositiveSmallIntegerField(default=0)
    source = models.CharField(
        max_length=10, choices=JourneyItem.Source.choices, default=JourneyItem.Source.USER,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "journey_checklist_items"
        ordering = ["position", "id"]

    def __str__(self):
        return self.text


class JourneyReference(models.Model):
    """Transport or stay details the user entered — not a booking we made."""

    class Kind(models.TextChoices):
        TRANSPORT = "transport", "Transport"
        ACCOMMODATION = "accommodation", "Accommodation"

    MAX_PER_JOURNEY = 30

    journey = models.ForeignKey(JourneyPlan, on_delete=models.CASCADE, related_name="references")
    kind = models.CharField(max_length=14, choices=Kind.choices)
    title = models.CharField(max_length=120)
    provider = models.CharField(max_length=100, blank=True)
    booking_reference = models.CharField(max_length=60, blank=True)
    url = models.URLField(max_length=300, blank=True)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    notes = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "journey_references"
        ordering = ["kind", "start_date", "id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(start_date__isnull=True)
                | Q(end_date__isnull=True)
                | Q(end_date__gte=F("start_date")),
                name="journey_reference_dates_ordered",
            ),
        ]

    def __str__(self):
        return self.title
