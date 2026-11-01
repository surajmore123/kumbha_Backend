"""
Lost & Found cases.

Kumbh Path helps families and registered helpers coordinate. It is not a police
or government system, and these records are not official reports.

A case is private: only the people in `apps.lostfound.policy` can reach it. Its
history can't be edited. Nothing here decides who a person is: a match is a
suggestion for staff, and only a person can confirm one or record a reunion.
"""

import secrets
import uuid

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.core.validators import MaxValueValidator
from django.db import models
from django.db.models import F, Q

from apps.family.models import FamilyCircle, FamilyMember
from apps.safety.models import SafetyAlert

_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def new_reference():
    return "LF-" + "".join(secrets.choice(_ALPHABET) for _ in range(8))


class Status(models.TextChoices):
    SUBMITTED = "SUBMITTED", "Submitted"
    UNDER_REVIEW = "UNDER_REVIEW", "Under review"
    VERIFICATION_REQUIRED = "VERIFICATION_REQUIRED", "Verification required"
    POTENTIAL_MATCH_FOUND = "POTENTIAL_MATCH_FOUND", "Potential match found"
    MATCH_CONFIRMED = "MATCH_CONFIRMED", "Match confirmed"
    REUNITED = "REUNITED", "Reunited"
    CLOSED = "CLOSED", "Closed"
    REJECTED = "REJECTED", "Rejected"


ACTIVE_STATUSES = (
    Status.SUBMITTED, Status.UNDER_REVIEW, Status.VERIFICATION_REQUIRED,
    Status.POTENTIAL_MATCH_FOUND, Status.MATCH_CONFIRMED,
)
_ACTIVE = [s.value for s in ACTIVE_STATUSES]


class LostFoundCase(models.Model):
    class Type(models.TextChoices):
        LOST = "lost", "Missing person"
        FOUND = "found", "Found person"

    class FoundCategory(models.TextChoices):
        FOUND = "found", "Person found"
        SEPARATED = "separated", "Separated from family"
        CHILD = "child_alone", "Child found without guardian"
        ELDERLY = "elderly", "Elderly person requiring assistance"
        MEDICAL = "medical", "Medical assistance required"
        OTHER = "other", "Other assistance required"

    class Contact(models.TextChoices):
        APP = "app", "In the app"
        CALL = "call", "Phone call"
        SMS = "sms", "SMS"
        WHATSAPP = "whatsapp", "WhatsApp"

    VULNERABILITIES = ("child", "elderly", "medical", "communication", "other")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    reference = models.CharField(max_length=16, unique=True, default=new_reference, editable=False)
    case_type = models.CharField(max_length=5, choices=Type.choices)
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.SUBMITTED)

    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="lostfound_reports",
    )
    # pilgrim, or the helper role they held when reporting.
    reporter_role = models.CharField(max_length=12, default="pilgrim")
    # Made by the app, so a retried submission can't create a second case.
    client_id = models.UUIDField(null=True, blank=True, editable=False)
    family = models.ForeignKey(
        FamilyCircle, on_delete=models.SET_NULL, null=True, blank=True, related_name="lostfound_cases",
    )
    member = models.ForeignKey(
        FamilyMember, on_delete=models.SET_NULL, null=True, blank=True, related_name="lostfound_cases",
    )
    alert = models.ForeignKey(
        SafetyAlert, on_delete=models.SET_NULL, null=True, blank=True, related_name="lostfound_cases",
    )

    person_name = models.CharField(max_length=120, blank=True)
    age_min = models.PositiveSmallIntegerField(null=True, blank=True, validators=[MaxValueValidator(120)])
    age_max = models.PositiveSmallIntegerField(null=True, blank=True, validators=[MaxValueValidator(120)])
    gender = models.CharField(max_length=20, blank=True, help_text="Optional. Never used for matching.")
    physical_description = models.TextField(max_length=1000, blank=True)
    clothing_description = models.TextField(max_length=1000, blank=True)
    identifying_marks = models.TextField(max_length=500, blank=True)
    circumstances = models.TextField(max_length=1000, blank=True)
    relationship = models.CharField(max_length=60, blank=True)
    preferred_contact = models.CharField(max_length=10, choices=Contact.choices, default=Contact.APP)
    vulnerabilities = models.JSONField(default=list, blank=True)

    found_category = models.CharField(max_length=12, choices=FoundCategory.choices, blank=True)
    assistance_needed = models.TextField(max_length=500, blank=True)
    safe_facility = models.CharField(max_length=160, blank=True, help_text="Where the person is being kept safe.")

    # When last seen (lost) or when found (found).
    event_at = models.DateTimeField()
    location_text = models.CharField(max_length=240)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)

    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="assigned_cases",
    )
    # Set from the coordinates when they fall in a zone. An unzoned case stays
    # visible to coordinators, so nothing can be lost between zones.
    zone = models.ForeignKey(
        "crowd.Zone", on_delete=models.SET_NULL, null=True, blank=True, related_name="lostfound_cases",
    )
    family_confirmed_at = models.DateTimeField(null=True, blank=True)
    reunited_at = models.DateTimeField(null=True, blank=True)
    reunited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["case_type", "status"]),
            models.Index(fields=["reporter", "-created_at"]),
            models.Index(fields=["family", "status"]),
            models.Index(fields=["assigned_to", "status"]),
            models.Index(fields=["zone", "status"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["reporter", "client_id"], condition=Q(client_id__isnull=False),
                name="lostfound_one_case_per_client_id",
            ),
            models.UniqueConstraint(
                fields=["member", "case_type"], condition=Q(member__isnull=False, status__in=_ACTIVE),
                name="lostfound_one_active_case_per_member",
            ),
            models.CheckConstraint(
                condition=Q(age_min__isnull=True) | Q(age_max__isnull=True) | Q(age_min__lte=F("age_max")),
                name="lostfound_age_range_in_order",
            ),
            models.CheckConstraint(
                condition=(
                    Q(latitude__isnull=True, longitude__isnull=True)
                    | Q(latitude__isnull=False, longitude__isnull=False)
                ),
                name="lostfound_location_is_complete",
            ),
        ]

    def __str__(self):
        return self.reference

    @property
    def is_active(self):
        return self.status in _ACTIVE

    @property
    def is_vulnerable(self):
        """Stricter handling for location, photos and release."""
        return bool(self.vulnerabilities) or self.found_category in (
            self.FoundCategory.CHILD, self.FoundCategory.ELDERLY, self.FoundCategory.MEDICAL,
        ) or (self.member_id is not None and self.member.is_dependent)

    @property
    def is_child(self):
        return "child" in self.vulnerabilities or self.found_category == self.FoundCategory.CHILD


class _Immutable(models.Model):
    """History can be added to, never changed or removed through the app."""

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise PermissionDenied("History can't be changed.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionDenied("History can't be removed.")


class CaseStatusHistory(_Immutable):
    id = models.BigAutoField(primary_key=True)
    case = models.ForeignKey(LostFoundCase, on_delete=models.CASCADE, related_name="status_history")
    from_status = models.CharField(max_length=24, blank=True)
    to_status = models.CharField(max_length=24)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    reason = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]


class CaseAudit(_Immutable):
    """Sensitive actions on a case. Holds ids and field names, not details."""

    id = models.BigAutoField(primary_key=True)
    case = models.ForeignKey(LostFoundCase, on_delete=models.CASCADE, related_name="audit")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    action = models.CharField(max_length=40, db_index=True)
    details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]


class CaseNote(models.Model):
    class Kind(models.TextChoices):
        INTERNAL = "internal", "Internal note"
        FAMILY_UPDATE = "family_update", "Update for the family"
        INFO_REQUEST = "info_request", "Information requested"
        FAMILY_INFO = "family_info", "Information from the family"
        CORRECTION = "correction", "Correction requested"
        VERIFICATION = "verification", "Verification result"

    FAMILY_VISIBLE = (Kind.FAMILY_UPDATE, Kind.INFO_REQUEST, Kind.FAMILY_INFO, Kind.CORRECTION)

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    case = models.ForeignKey(LostFoundCase, on_delete=models.CASCADE, related_name="notes")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    kind = models.CharField(max_length=14, choices=Kind.choices)
    body = models.TextField(max_length=1000)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [models.Index(fields=["case", "kind"])]


class CaseSighting(models.Model):
    class Review(models.TextChoices):
        PENDING = "pending", "Waiting for review"
        APPROVED = "approved", "Reviewed by staff"
        REJECTED = "rejected", "Not used"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    case = models.ForeignKey(LostFoundCase, on_delete=models.CASCADE, related_name="sightings")
    reported_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    reporter_role = models.CharField(max_length=12, default="pilgrim")
    description = models.TextField(max_length=1000)
    location_text = models.CharField(max_length=240)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    seen_at = models.DateTimeField()
    review = models.CharField(max_length=8, choices=Review.choices, default=Review.PENDING)
    # Approved means "staff think this is worth sharing". Verified means staff
    # checked it first-hand. Families are shown which.
    verified = models.BooleanField(default=False)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-seen_at"]
        indexes = [models.Index(fields=["case", "review"])]


class CaseMatch(models.Model):
    """A suggestion for staff. The score is never proof of anything."""

    class State(models.TextChoices):
        SUGGESTED = "suggested", "Suggested"
        APPROVED = "approved", "Approved for checking"
        DISMISSED = "dismissed", "Dismissed"
        CONFIRMED = "confirmed", "Confirmed by staff"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    lost_case = models.ForeignKey(LostFoundCase, on_delete=models.CASCADE, related_name="matches_as_lost")
    found_case = models.ForeignKey(LostFoundCase, on_delete=models.CASCADE, related_name="matches_as_found")
    score = models.PositiveSmallIntegerField()
    reasons = models.JSONField(default=list)
    state = models.CharField(max_length=10, choices=State.choices, default=State.SUGGESTED)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-score", "-created_at"]
        indexes = [models.Index(fields=["state", "-score"])]
        constraints = [
            models.UniqueConstraint(fields=["lost_case", "found_case"], name="lostfound_one_match_per_pair"),
        ]


class CaseAttachment(models.Model):
    """Held in the database, not /media/, because media files are public and
    many of these show children. Served only after a permission check."""

    MAX_PER_CASE = 5
    MAX_BYTES = 6 * 1024 * 1024

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    case = models.ForeignKey(LostFoundCase, on_delete=models.CASCADE, related_name="attachments")
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    client_id = models.UUIDField(null=True, blank=True, editable=False)
    content_type = models.CharField(max_length=40)
    data = models.BinaryField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["case", "client_id"], condition=Q(client_id__isnull=False),
                name="lostfound_one_upload_per_client_id",
            ),
        ]


class CaseNotification(models.Model):
    """The outbox. A row survives a failed send, and the key stops the same
    event reaching the same person twice."""

    class State(models.TextChoices):
        PENDING = "pending", "Waiting to send"
        SENT = "sent", "Sent"
        NO_DEVICE = "no_device", "No device or turned off"
        FAILED = "failed", "Gave up"

    MAX_ATTEMPTS = 5

    id = models.BigAutoField(primary_key=True)
    case = models.ForeignKey(LostFoundCase, on_delete=models.CASCADE, related_name="notifications")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    event = models.CharField(max_length=24)
    key = models.CharField(max_length=80)
    for_staff = models.BooleanField(default=False)
    state = models.CharField(max_length=10, choices=State.choices, default=State.PENDING, db_index=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    next_attempt_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["case", "user", "key"], name="lostfound_one_notification_per_event"),
        ]


class CaseTranslation(models.Model):
    """A machine translation, kept beside the original and never replacing it.
    `source_text` is what was translated, so a later edit shows it's out of date."""

    class Source(models.TextChoices):
        FIELD = "field", "Case field"
        NOTE = "note", "Case note"
        SIGHTING = "sighting", "Sighting"

    class Review(models.TextChoices):
        AI = "ai", "AI translated, not reviewed"
        ACCEPTED = "accepted", "Reviewed by a person"
        CORRECTED = "corrected", "Corrected by a person"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    case = models.ForeignKey(LostFoundCase, on_delete=models.CASCADE, related_name="translations")
    source_type = models.CharField(max_length=8, choices=Source.choices)
    source_ref = models.CharField(max_length=40)
    source_text = models.TextField()
    source_language = models.CharField(max_length=8)
    target_language = models.CharField(max_length=2)
    machine_text = models.TextField()
    reviewed_text = models.TextField(blank=True)
    is_uncertain = models.BooleanField(default=False)
    review = models.CharField(max_length=9, choices=Review.choices, default=Review.AI)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["case", "source_type", "source_ref", "target_language"],
                name="lostfound_one_translation",
            ),
        ]


class CaseExtraction(models.Model):
    """Details an AI read out of a report. Never written onto the case: the
    matcher uses them only after a person has reviewed them."""

    class Review(models.TextChoices):
        AI = "ai", "AI generated, not reviewed"
        ACCEPTED = "accepted", "Reviewed by a person"
        REJECTED = "rejected", "Rejected by a person"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    case = models.OneToOneField(LostFoundCase, on_delete=models.CASCADE, related_name="ai_extraction")
    source_text = models.TextField()
    machine_fields = models.JSONField(default=dict)
    reviewed_fields = models.JSONField(default=dict, blank=True)
    review = models.CharField(max_length=8, choices=Review.choices, default=Review.AI)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
