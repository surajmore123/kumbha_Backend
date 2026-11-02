import re

from rest_framework import serializers

from apps.aiChat.services.geo import distance_km
from apps.akhadas.serializers import SourceSerializer, image_of
from apps.bookings import models
from apps.temples.models import Temple


def _named(obj, language):
    return getattr(obj, f"name_{language}", "") or obj.name


def _digits_look_like_a_card(value):
    """Card numbers are 13–19 digits passing the Luhn check."""
    for run in re.findall(r"(?:\d[ -]?){13,19}", value or ""):
        digits = [int(d) for d in re.sub(r"\D", "", run)]
        if not 13 <= len(digits) <= 19:
            continue
        total = sum(
            d if i % 2 == 0 else (d * 2 - 9 if d * 2 > 9 else d * 2)
            for i, d in enumerate(reversed(digits))
        )
        if total % 10 == 0:
            return True
    return False


class AreaSerializer(serializers.ModelSerializer):
    name = serializers.SerializerMethodField()
    image = serializers.SerializerMethodField()

    class Meta:
        model = models.StayArea
        fields = ["slug", "name", "image"]

    def get_name(self, obj):
        return _named(obj, self.context.get("language", "en"))

    def get_image(self, obj):
        return image_of(obj, self.context.get("request"))


class AmenitySerializer(serializers.ModelSerializer):
    name = serializers.SerializerMethodField()

    class Meta:
        model = models.Amenity
        fields = ["slug", "name"]

    def get_name(self, obj):
        return _named(obj, self.context.get("language", "en"))


class StaySummarySerializer(serializers.ModelSerializer):
    """`distance_km` is straight-line, from the place the pilgrim chose."""

    id = serializers.CharField(source="listing_id")
    name = serializers.CharField(source="listing.name")
    price_from = serializers.SerializerMethodField()
    price_unit = serializers.CharField(source="listing.unit")
    accessible = serializers.BooleanField(source="listing.wheelchair")
    area = AreaSerializer(read_only=True)
    amenities = AmenitySerializer(many=True, read_only=True)
    image = serializers.SerializerMethodField()
    distance_km = serializers.SerializerMethodField()

    class Meta:
        model = models.StayProfile
        fields = [
            "id", "name", "stay_type", "area", "amenities", "image", "price_from",
            "price_unit", "price_status", "availability_verified", "accessible",
            "family_friendly", "senior_friendly", "verification_status",
            "last_verified_on", "distance_km",
        ]

    def get_price_from(self, obj):
        # 0 means "see rates" in the catalogue; never show it as a price.
        return obj.listing.price_from or None

    def get_image(self, obj):
        request = self.context.get("request")
        for image in obj.images.all():
            shown = image_of(image, request)
            if shown:
                return shown
        # An area photograph is never passed off as the property.
        area = image_of(obj.area, request)
        return {**area, "representative": True} if area else None

    def get_distance_km(self, obj):
        origin = self.context.get("origin")
        if origin is None or not obj.has_coordinates:
            return None
        return round(distance_km(origin[0], origin[1], obj.latitude, obj.longitude), 1)


class RoomSerializer(serializers.ModelSerializer):
    name = serializers.SerializerMethodField()

    class Meta:
        model = models.StayRoom
        fields = ["name", "price"]

    def get_name(self, obj):
        return _named(obj, self.context.get("language", "en"))


class StayDetailSerializer(StaySummarySerializer):
    rooms = RoomSerializer(many=True, read_only=True)
    images = serializers.SerializerMethodField()
    sources = SourceSerializer(many=True, read_only=True)
    landmarks = serializers.SerializerMethodField()
    text = serializers.SerializerMethodField()
    provider = serializers.SerializerMethodField()
    latitude = serializers.FloatField(allow_null=True)
    longitude = serializers.FloatField(allow_null=True)

    class Meta(StaySummarySerializer.Meta):
        fields = StaySummarySerializer.Meta.fields + [
            "address", "latitude", "longitude", "phone", "email", "website_url",
            "booking_url", "rooms", "images", "sources", "landmarks", "text", "provider",
        ]

    def get_images(self, obj):
        request = self.context.get("request")
        shown = []
        for image in obj.images.all():
            data = image_of(image, request)
            if data:
                shown.append({**data, "caption": image.caption})
        return shown

    def get_text(self, obj):
        language = self.context.get("language", "en")
        rows = {row.language: row for row in obj.texts.all()}
        row = rows.get(language) or rows.get("en")
        return {
            "overview": row.overview if row else "",
            "booking_instructions": row.booking_instructions if row else "",
            "cancellation_policy": row.cancellation_policy if row else "",
            "price_note": row.price_note if row else "",
            "content_language": row.language if row else None,
        }

    def get_provider(self, obj):
        partner = obj.listing.partner
        return partner.name if partner and partner.status == "verified" else None

    def get_landmarks(self, obj):
        """Straight-line distances to the main places, from existing records."""
        if not obj.has_coordinates:
            return []
        places = [
            (_named(a, self.context.get("language", "en")), a.latitude, a.longitude)
            for a in models.StayArea.objects.exclude(latitude=None)
        ]
        distances = [
            {"name": name, "distance_km": round(distance_km(obj.latitude, obj.longitude, lat, lng), 1)}
            for name, lat, lng in places
        ]
        return sorted(distances, key=lambda d: d["distance_km"])


class TransportProviderSerializer(serializers.ModelSerializer):
    note = serializers.SerializerMethodField()
    url = serializers.SerializerMethodField()

    class Meta:
        model = models.TransportProvider
        fields = ["slug", "mode", "name", "is_official", "url", "can_book", "integration", "note", "last_verified_on"]

    def get_note(self, obj):
        language = self.context.get("language", "en")
        return getattr(obj, f"note_{language}", "") or obj.note

    def get_url(self, obj):
        return obj.action_url or obj.website_url


class SavedBookingSerializer(serializers.ModelSerializer):
    journey = serializers.PrimaryKeyRelatedField(
        queryset=models.JourneyPlan.objects.none(), required=False, allow_null=True,
    )
    stay_id = serializers.CharField(source="stay.listing_id", read_only=True, default=None)
    stay_listing = serializers.CharField(write_only=True, required=False, allow_null=True, allow_blank=True)

    class Meta:
        model = models.SavedBooking
        fields = [
            "id", "category", "status", "title", "provider", "reference", "start_date",
            "end_date", "start_time", "from_place", "to_place", "people", "traveller_names",
            "amount_paid", "booking_url", "notes", "journey", "stay_id", "stay_listing",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if request is not None and request.user.is_authenticated:
            # A journey can only be linked by its owner.
            self.fields["journey"].queryset = models.JourneyPlan.objects.filter(user=request.user)

    def validate_title(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Give this booking a name.")
        return value

    def validate_booking_url(self, value):
        if value and not value.lower().startswith("https://"):
            raise serializers.ValidationError("Use an https:// link.")
        return value

    def validate(self, attrs):
        for field in ("reference", "notes", "traveller_names", "title"):
            if _digits_look_like_a_card(attrs.get(field, "")):
                raise serializers.ValidationError({
                    field: "This looks like a card number. Please don't save payment details here.",
                })
        start = attrs.get("start_date", getattr(self.instance, "start_date", None))
        end = attrs.get("end_date", getattr(self.instance, "end_date", None))
        if end and not start:
            raise serializers.ValidationError({"start_date": "Add the start date."})
        if start and end and end < start:
            raise serializers.ValidationError({"end_date": "End date must be on or after the start date."})
        amount = attrs.get("amount_paid")
        if amount is not None and amount > 10_000_000:
            raise serializers.ValidationError({"amount_paid": "Enter an amount up to 1,00,00,000."})
        return attrs

    def _attach_stay(self, validated):
        listing_id = validated.pop("stay_listing", None)
        if listing_id:
            validated["stay"] = models.StayProfile.objects.filter(listing_id=listing_id).first()

    def create(self, validated):
        self._attach_stay(validated)
        return super().create(validated)

    def update(self, instance, validated):
        self._attach_stay(validated)
        return super().update(instance, validated)


def nearest_temples(stay, limit=3):
    """Closest active temples, from the Temple table."""
    if not stay.has_coordinates:
        return []
    temples = Temple.objects.filter(is_active=True, del_flag=0)
    ranked = sorted(
        (
            {
                "id": str(t.temple_id), "name": t.name,
                "distance_km": round(distance_km(stay.latitude, stay.longitude, t.latitude, t.longitude), 1),
            }
            for t in temples
        ),
        key=lambda t: t["distance_km"],
    )
    return ranked[:limit]
