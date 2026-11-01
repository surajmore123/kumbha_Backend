from datetime import timedelta

from django.utils import timezone
from rest_framework import serializers

from apps.lostfound import ai, matching, policy
from apps.lostfound.models import (
    CaseExtraction,
    CaseMatch,
    CaseNote,
    CaseSighting,
    CaseTranslation,
    LostFoundCase,
    Status,
)


def _not_future(value):
    if value > timezone.now() + timedelta(minutes=10):
        raise serializers.ValidationError("This time is in the future.")
    return value


class _Location(serializers.Serializer):
    latitude = serializers.FloatField(required=False, allow_null=True, min_value=-90, max_value=90)
    longitude = serializers.FloatField(required=False, allow_null=True, min_value=-180, max_value=180)

    def validate(self, attrs):
        if (attrs.get("latitude") is None) != (attrs.get("longitude") is None):
            raise serializers.ValidationError({"latitude": "Send both coordinates, or neither."})
        return attrs


class _Report(_Location):
    client_id = serializers.UUIDField(required=False, allow_null=True)
    person_name = serializers.CharField(max_length=120, required=False, allow_blank=True)
    age_min = serializers.IntegerField(required=False, allow_null=True, min_value=0, max_value=120)
    age_max = serializers.IntegerField(required=False, allow_null=True, min_value=0, max_value=120)
    gender = serializers.CharField(max_length=20, required=False, allow_blank=True)
    physical_description = serializers.CharField(max_length=1000, required=False, allow_blank=True)
    clothing_description = serializers.CharField(max_length=1000, required=False, allow_blank=True)
    identifying_marks = serializers.CharField(max_length=500, required=False, allow_blank=True)
    vulnerabilities = serializers.ListField(
        child=serializers.ChoiceField(choices=LostFoundCase.VULNERABILITIES), required=False,
    )
    event_at = serializers.DateTimeField(validators=[_not_future])
    location_text = serializers.CharField(max_length=240)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        low, high = attrs.get("age_min"), attrs.get("age_max")
        if low is not None and high is not None and low > high:
            raise serializers.ValidationError({"age_max": "The age range is the wrong way round."})
        if not attrs.get("physical_description", "").strip() and not attrs.get("clothing_description", "").strip():
            raise serializers.ValidationError({"physical_description": "Describe the person or their clothing."})
        return attrs


class LostReportSerializer(_Report):
    family_id = serializers.UUIDField(required=False, allow_null=True)
    member_id = serializers.UUIDField(required=False, allow_null=True)
    circumstances = serializers.CharField(max_length=1000, required=False, allow_blank=True)
    relationship = serializers.CharField(max_length=60)
    preferred_contact = serializers.ChoiceField(choices=LostFoundCase.Contact.choices, required=False)


class FoundReportSerializer(_Report):
    found_category = serializers.ChoiceField(choices=LostFoundCase.FoundCategory.choices)
    assistance_needed = serializers.CharField(max_length=500, required=False, allow_blank=True)
    safe_facility = serializers.CharField(max_length=160, required=False, allow_blank=True)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if attrs["found_category"] == LostFoundCase.FoundCategory.CHILD and not attrs.get("safe_facility", "").strip():
            raise serializers.ValidationError({"safe_facility": "Say which help desk the child is being kept safe at."})
        return attrs


class SightingInputSerializer(_Location):
    description = serializers.CharField(max_length=1000)
    location_text = serializers.CharField(max_length=240)
    seen_at = serializers.DateTimeField(validators=[_not_future])


class TextSerializer(serializers.Serializer):
    body = serializers.CharField(max_length=1000)


class StatusChangeSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=Status.choices)
    reason = serializers.CharField(max_length=500)


class NoteSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=[
        CaseNote.Kind.INTERNAL, CaseNote.Kind.FAMILY_UPDATE, CaseNote.Kind.INFO_REQUEST,
    ])
    body = serializers.CharField(max_length=1000)


class CheckSerializer(serializers.Serializer):
    method = serializers.ChoiceField(choices=["id_document", "known_to_staff", "family_in_person", "other"])
    remarks = serializers.CharField(max_length=800)


class ReunionSerializer(CheckSerializer):
    identity_checked = serializers.BooleanField()
    person_recognised = serializers.BooleanField(required=False, default=False)


def _location_label(sighting):
    return "verified" if sighting.verified else "reported"


class CaseListSerializer(serializers.ModelSerializer):
    latest_update = serializers.SerializerMethodField()

    class Meta:
        model = LostFoundCase
        fields = ["id", "reference", "case_type", "status", "person_name", "created_at", "latest_update"]

    def get_latest_update(self, obj):
        return obj.updated_at


class FamilyCaseSerializer(serializers.ModelSerializer):
    """What the family side sees. No internal notes, no staff names, no reasons,
    and no pending sightings."""

    timeline = serializers.SerializerMethodField()
    sightings = serializers.SerializerMethodField()
    latitude = serializers.SerializerMethodField()
    longitude = serializers.SerializerMethodField()
    has_photo = serializers.SerializerMethodField()
    is_my_report = serializers.SerializerMethodField()
    attachment_ids = serializers.SerializerMethodField()

    class Meta:
        model = LostFoundCase
        fields = [
            "id", "reference", "case_type", "status", "person_name", "age_min", "age_max",
            "physical_description", "clothing_description", "identifying_marks", "circumstances",
            "vulnerabilities", "found_category", "safe_facility", "event_at", "location_text",
            "latitude", "longitude", "has_photo", "attachment_ids", "timeline", "sightings",
            "family_confirmed_at", "created_at", "updated_at", "is_my_report",
        ]

    def _user(self):
        return self.context["request"].user

    def _coordinate(self, obj, value):
        if value is None or not policy.can_see_location(self._user(), obj):
            return None
        return float(value)

    def get_latitude(self, obj):
        return self._coordinate(obj, obj.latitude)

    def get_longitude(self, obj):
        return self._coordinate(obj, obj.longitude)

    def get_has_photo(self, obj):
        return obj.attachments.exists()

    def get_attachment_ids(self, obj):
        return [str(pk) for pk in obj.attachments.values_list("id", flat=True)]

    def get_is_my_report(self, obj):
        return obj.reporter_id == self._user().pk

    def get_timeline(self, obj):
        events = [
            {"kind": "status", "status": h.to_status, "at": h.created_at}
            for h in obj.status_history.all()
        ]
        events += [
            {"kind": "note", "note_kind": n.kind, "body": n.body, "at": n.created_at}
            for n in obj.notes.all() if n.kind in CaseNote.FAMILY_VISIBLE
        ]
        return sorted(events, key=lambda e: e["at"], reverse=True)

    def get_sightings(self, obj):
        rows = obj.sightings.filter(review=CaseSighting.Review.APPROVED)
        show_place = policy.can_see_location(self._user(), obj)
        return [{
            "id": str(s.pk), "description": s.description, "seen_at": s.seen_at,
            "location_text": s.location_text if show_place else "",
            "latitude": float(s.latitude) if show_place and s.latitude is not None else None,
            "longitude": float(s.longitude) if show_place and s.longitude is not None else None,
            "location_label": _location_label(s),
            "source": "helper" if s.reporter_role != "pilgrim" else "community",
        } for s in rows]


class HelperCaseSerializer(serializers.ModelSerializer):
    """A helper's own found report: what they sent and where it stands."""

    class Meta:
        model = LostFoundCase
        fields = [
            "id", "reference", "case_type", "status", "found_category", "safe_facility", "event_at",
            "location_text", "created_at", "updated_at",
        ]


class OpsListSerializer(serializers.ModelSerializer):
    match_count = serializers.SerializerMethodField()
    is_vulnerable = serializers.BooleanField(read_only=True)
    assigned_to_me = serializers.SerializerMethodField()

    class Meta:
        model = LostFoundCase
        fields = [
            "id", "reference", "case_type", "status", "person_name", "location_text", "event_at",
            "created_at", "is_vulnerable", "match_count", "assigned_to_me",
        ]

    def get_match_count(self, obj):
        counted = getattr(obj, "open_match_count", None)
        if counted is not None:
            return counted
        return obj.matches_as_lost.filter(state__in=["suggested", "approved"]).count() + (
            obj.matches_as_found.filter(state__in=["suggested", "approved"]).count()
        )

    def get_assigned_to_me(self, obj):
        return obj.assigned_to_id == self.context["request"].user.pk


class OpsNoteSerializer(serializers.ModelSerializer):
    class Meta:
        model = CaseNote
        fields = ["id", "kind", "body", "created_at"]


class OpsSightingSerializer(serializers.ModelSerializer):
    class Meta:
        model = CaseSighting
        fields = [
            "id", "reporter_role", "description", "location_text", "latitude", "longitude", "seen_at",
            "review", "verified",
        ]


class OpsCaseSerializer(OpsListSerializer):
    """Everything except the reporter's number, which has its own logged route."""

    notes = OpsNoteSerializer(many=True, read_only=True)
    sightings = OpsSightingSerializer(many=True, read_only=True)
    history = serializers.SerializerMethodField()
    matches = serializers.SerializerMethodField()
    allowed_statuses = serializers.SerializerMethodField()
    attachment_ids = serializers.SerializerMethodField()
    linked_to_family = serializers.SerializerMethodField()

    class Meta(OpsListSerializer.Meta):
        fields = OpsListSerializer.Meta.fields + [
            "reporter_role", "age_min", "age_max", "gender", "physical_description", "clothing_description",
            "identifying_marks", "circumstances", "relationship", "preferred_contact", "vulnerabilities",
            "found_category", "assistance_needed", "safe_facility", "latitude", "longitude", "notes",
            "sightings", "history", "matches", "allowed_statuses", "attachment_ids", "linked_to_family",
            "family_confirmed_at",
        ]

    def get_history(self, obj):
        return [
            {"from": h.from_status, "to": h.to_status, "reason": h.reason, "at": h.created_at}
            for h in obj.status_history.all()
        ]

    def get_matches(self, obj):
        related = ("found_case__ai_extraction", "lost_case__ai_extraction")
        rows = list(obj.matches_as_lost.select_related(*related)) + list(
            obj.matches_as_found.select_related(*related),
        )
        return MatchSerializer(rows, many=True).data

    def get_allowed_statuses(self, obj):
        from apps.lostfound.services import _GUARDED, TRANSITIONS
        return sorted(s.value for s in TRANSITIONS.get(obj.status, set()) - _GUARDED)

    def get_attachment_ids(self, obj):
        return [str(pk) for pk in obj.attachments.values_list("id", flat=True)]

    def get_linked_to_family(self, obj):
        return obj.family_id is not None


class _MatchSide(serializers.ModelSerializer):
    class Meta:
        model = LostFoundCase
        fields = [
            "id", "reference", "status", "age_min", "age_max", "physical_description", "clothing_description",
            "location_text", "event_at",
        ]


class MatchSerializer(serializers.ModelSerializer):
    lost = _MatchSide(source="lost_case", read_only=True)
    found = _MatchSide(source="found_case", read_only=True)
    explanation = serializers.SerializerMethodField()

    class Meta:
        model = CaseMatch
        fields = ["id", "score", "reasons", "explanation", "state", "lost", "found", "created_at"]

    def get_explanation(self, obj):
        return matching.explain(obj.lost_case, obj.found_case)


class TranslateSerializer(serializers.Serializer):
    source_type = serializers.ChoiceField(choices=CaseTranslation.Source.choices)
    source_ref = serializers.CharField(max_length=40)
    target_language = serializers.ChoiceField(choices=ai.LANGUAGES)


class TranslationReviewSerializer(serializers.Serializer):
    text = serializers.CharField(max_length=4000, required=False, allow_blank=True, default="")


class ExtractionReviewSerializer(serializers.Serializer):
    accept = serializers.BooleanField()
    corrections = serializers.DictField(required=False, default=dict)


class TranslationSerializer(serializers.ModelSerializer):
    text = serializers.SerializerMethodField()
    is_ai = serializers.SerializerMethodField()
    is_stale = serializers.SerializerMethodField()

    class Meta:
        model = CaseTranslation
        fields = [
            "id", "source_type", "source_ref", "source_text", "source_language", "target_language", "text",
            "machine_text", "is_ai", "review", "is_uncertain", "is_stale", "reviewed_at",
        ]

    def get_text(self, obj):
        return obj.reviewed_text or obj.machine_text

    def get_is_ai(self, obj):
        return obj.review != CaseTranslation.Review.CORRECTED

    def get_is_stale(self, obj):
        return (ai.source_text(obj.case, obj.source_type, obj.source_ref) or "").strip() != obj.source_text


class ExtractionSerializer(serializers.ModelSerializer):
    missing = serializers.SerializerMethodField()

    class Meta:
        model = CaseExtraction
        fields = ["id", "review", "machine_fields", "reviewed_fields", "missing", "created_at", "reviewed_at"]

    def get_missing(self, obj):
        return [name for name in ai.EXTRACTED_FIELDS if name not in obj.machine_fields]
