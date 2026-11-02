"""
Booking & Stay.

Stays extend the website's `Listing` catalogue (one record per property), so
partner submissions and the mobile app share one source. KumbhaPath makes no
bookings: `SavedBooking` is the pilgrim's own record of one made elsewhere.
"""

import uuid
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q

from apps.akhadas.models import ContentSource, ImageRights, LANGUAGES, validate_https
from apps.journeys.models import JourneyPlan
from apps.website.models import Listing


def _unique_language(name):
    return models.UniqueConstraint(fields=["parent", "language"], name=f"bookings_{name}_language")


class StayArea(ImageRights):
    """A place pilgrims search by. Coordinates are set only where verified."""

    slug = models.SlugField(max_length=40, unique=True)
    position = models.PositiveSmallIntegerField(default=0)
    name = models.CharField(max_length=60)
    name_hi = models.CharField(max_length=60)
    name_mr = models.CharField(max_length=60)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)

    class Meta:
        ordering = ["position", "slug"]

    def __str__(self):
        return self.name


class Amenity(models.Model):
    slug = models.SlugField(max_length=40, unique=True)
    position = models.PositiveSmallIntegerField(default=0)
    name = models.CharField(max_length=60)
    name_hi = models.CharField(max_length=60)
    name_mr = models.CharField(max_length=60)

    class Meta:
        ordering = ["position", "slug"]
        verbose_name_plural = "Amenities"

    def __str__(self):
        return self.name


class StayProfile(models.Model):
    """What pilgrims need on top of a Listing. A stay appears in the app only
    when its Listing is published, real and not expired."""

    class StayType(models.TextChoices):
        HOTEL = "hotel", "Hotel"
        BUDGET = "budget", "Budget hotel"
        DHARAMSHALA = "dharamshala", "Dharamshala"
        ASHRAM = "ashram", "Ashram"
        GUEST_HOUSE = "guest_house", "Guest house"
        TENT = "tent", "Tent city"
        FAMILY = "family", "Family accommodation"
        OTHER = "other", "Other pilgrim accommodation"

    class Verification(models.TextChoices):
        VERIFIED = "verified", "Verified with an official or provider source"
        UNVERIFIED = "unverified", "Not yet verified"
        EXPIRED = "expired", "Expired: hide from the app"

    class PriceStatus(models.TextChoices):
        VERIFIED = "verified", "Published by the provider"
        ESTIMATED = "estimated", "Estimate"
        ON_REQUEST = "on_request", "Ask the provider"

    listing = models.OneToOneField(Listing, on_delete=models.CASCADE, related_name="stay")
    stay_type = models.CharField(max_length=12, choices=StayType.choices)
    area = models.ForeignKey(StayArea, on_delete=models.PROTECT, related_name="stays")
    address = models.CharField(max_length=250, blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    amenities = models.ManyToManyField(Amenity, blank=True, related_name="stays")
    family_friendly = models.BooleanField(default=False, help_text="Only from verified property information.")
    senior_friendly = models.BooleanField(default=False, help_text="Only from verified property information.")
    phone = models.CharField(max_length=40, blank=True, help_text="Published contact only.")
    email = models.EmailField(blank=True)
    website_url = models.URLField(max_length=300, blank=True, validators=[validate_https])
    booking_url = models.URLField(max_length=300, blank=True, validators=[validate_https])
    price_status = models.CharField(max_length=12, choices=PriceStatus.choices, default=PriceStatus.ON_REQUEST)
    availability_verified = models.BooleanField(
        default=False, help_text="Only when the provider has confirmed availability.",
    )
    verification_status = models.CharField(
        max_length=12, choices=Verification.choices, default=Verification.UNVERIFIED,
    )
    last_verified_on = models.DateField(null=True, blank=True)
    expires_on = models.DateField(null=True, blank=True, help_text="Hide after this date.")
    sources = models.ManyToManyField(ContentSource, blank=True, related_name="stay_profiles")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["stay_type"]),
            models.Index(fields=["verification_status", "expires_on"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(latitude__isnull=True, longitude__isnull=True)
                | Q(latitude__isnull=False, longitude__isnull=False),
                name="bookings_stay_coordinates_both_or_neither",
            ),
        ]

    def __str__(self):
        return self.listing.name

    def clean(self):
        super().clean()
        if self.verification_status == self.Verification.VERIFIED and not self.last_verified_on:
            raise ValidationError({"last_verified_on": "A verified stay needs its last verified date."})
        if self.availability_verified and self.verification_status != self.Verification.VERIFIED:
            raise ValidationError({"availability_verified": "Only a verified stay can show availability."})

    @property
    def has_coordinates(self):
        return self.latitude is not None and self.longitude is not None


class StayText(models.Model):
    parent = models.ForeignKey(StayProfile, on_delete=models.CASCADE, related_name="texts")
    language = models.CharField(max_length=2, choices=LANGUAGES)
    overview = models.TextField()
    booking_instructions = models.TextField(blank=True)
    cancellation_policy = models.TextField(blank=True, help_text="Only what the provider publishes.")
    price_note = models.CharField(max_length=200, blank=True)

    class Meta:
        constraints = [_unique_language("stay")]


class StayRoom(models.Model):
    stay = models.ForeignKey(StayProfile, on_delete=models.CASCADE, related_name="rooms")
    position = models.PositiveSmallIntegerField(default=0)
    name = models.CharField(max_length=80)
    name_hi = models.CharField(max_length=80, blank=True)
    name_mr = models.CharField(max_length=80, blank=True)
    price = models.PositiveIntegerField(null=True, blank=True, help_text="Whole rupees. Empty if not published.")

    class Meta:
        ordering = ["position", "id"]

    def __str__(self):
        return self.name


class StayImage(ImageRights):
    """A genuine photograph of the property, with its usage basis."""

    stay = models.ForeignKey(StayProfile, on_delete=models.CASCADE, related_name="images")
    position = models.PositiveSmallIntegerField(default=0)
    caption = models.CharField(max_length=160, blank=True)

    class Meta:
        ordering = ["position", "id"]


class TransportProvider(models.Model):
    """A provider people can be sent to. `integration` says what we really have."""

    class Mode(models.TextChoices):
        TRAIN = "train", "Train"
        BUS = "bus", "Bus"
        FLIGHT = "flight", "Flight"
        TAXI = "taxi", "Taxi and cab"
        LOCAL = "local", "Local transport"

    class Integration(models.TextChoices):
        LINK = "link", "Opens the provider's site"
        API = "api", "Live results from an authorized API"

    slug = models.SlugField(max_length=50, unique=True)
    position = models.PositiveSmallIntegerField(default=0)
    mode = models.CharField(max_length=8, choices=Mode.choices, db_index=True)
    name = models.CharField(max_length=120)
    is_official = models.BooleanField(default=False)
    website_url = models.URLField(max_length=300, validators=[validate_https])
    action_url = models.URLField(max_length=300, blank=True, validators=[validate_https])
    integration = models.CharField(max_length=6, choices=Integration.choices, default=Integration.LINK)
    can_book = models.BooleanField(default=False, help_text="Tickets can be bought at this link.")
    note = models.CharField(max_length=250, blank=True)
    note_hi = models.CharField(max_length=250, blank=True)
    note_mr = models.CharField(max_length=250, blank=True)
    is_active = models.BooleanField(default=True)
    last_verified_on = models.DateField(null=True, blank=True)
    terms_notes = models.TextField(blank=True, help_text="Internal: access and terms findings.")

    class Meta:
        ordering = ["mode", "position", "slug"]

    def __str__(self):
        return self.name


class SavedBooking(models.Model):
    """The pilgrim's own note of a booking made with a provider. Status is what
    they entered; KumbhaPath has not checked it."""

    class Category(models.TextChoices):
        STAY = "stay", "Accommodation"
        TRAIN = "train", "Train"
        BUS = "bus", "Bus"
        FLIGHT = "flight", "Flight"
        TAXI = "taxi", "Taxi or local transport"

    class Status(models.TextChoices):
        SAVED = "saved", "Saved"
        PENDING = "pending", "Pending confirmation"
        CONFIRMED = "confirmed", "Confirmed by provider"
        CANCELLED = "cancelled", "Cancelled"
        COMPLETED = "completed", "Completed"

    MAX_PER_USER = 100

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="saved_bookings")
    journey = models.ForeignKey(
        JourneyPlan, on_delete=models.SET_NULL, null=True, blank=True, related_name="saved_bookings",
    )
    stay = models.ForeignKey(
        StayProfile, on_delete=models.SET_NULL, null=True, blank=True, related_name="saved_bookings",
    )
    category = models.CharField(max_length=8, choices=Category.choices)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.SAVED)
    title = models.CharField(max_length=120)
    provider = models.CharField(max_length=100, blank=True)
    reference = models.CharField(max_length=40, blank=True, help_text="PNR or booking number.")
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    start_time = models.TimeField(null=True, blank=True)
    from_place = models.CharField(max_length=100, blank=True)
    to_place = models.CharField(max_length=100, blank=True)
    people = models.PositiveSmallIntegerField(default=1, validators=[MinValueValidator(1)])
    traveller_names = models.CharField(max_length=200, blank=True)
    amount_paid = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(Decimal("0"))],
    )
    booking_url = models.URLField(max_length=300, blank=True, validators=[validate_https])
    notes = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["start_date", "-created_at"]
        indexes = [
            models.Index(fields=["user", "start_date"]),
            models.Index(fields=["user", "status"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(end_date__isnull=True) | Q(start_date__isnull=False, end_date__gte=models.F("start_date")),
                name="bookings_saved_dates",
            ),
        ]

    def __str__(self):
        return self.title
