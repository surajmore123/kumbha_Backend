"""
Family reunification: safe meeting points, and the plan to meet on a case.

This adds no location or case records of its own. Family positions stay in
`apps.familylocation` and case facts in `apps.lostfound`. A meeting point says
how far it can be trusted, and only staff can raise that. No record here is
official unless staff name the official source, and nothing here can mark
anyone reunited: that takes a recorded human check in `apps.lostfound`.
"""

import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.family.models import FamilyCircle
from apps.lostfound.models import LostFoundCase


class MeetingPoint(models.Model):
    class Category(models.TextChoices):
        HELP_DESK = "help_desk", "Help desk"
        POLICE = "police", "Police assistance booth"
        LOST_FOUND = "lost_found", "Lost & Found centre"
        MEDICAL = "medical", "Medical camp"
        HOSPITAL = "hospital", "Hospital"
        AMBULANCE = "ambulance", "Ambulance facility"
        FIRE_RESCUE = "fire_rescue", "Fire and rescue service"
        EMERGENCY = "emergency", "Emergency assistance point"
        FAMILY_MEETING = "family_meeting", "Family meeting point"

    class Status(models.TextChoices):
        FAMILY = "family", "Private to one family"
        SUGGESTED = "suggested", "Suggested, waiting for staff"
        COMMUNITY = "community", "Community suggestion, not verified"
        VERIFIED = "verified", "Verified by staff"
        RETIRED = "retired", "No longer in use"

    class Source(models.TextChoices):
        OFFICIAL = "official", "Published by an official body"
        FIELD_CHECK = "field_check", "Checked in person by staff"
        COMMUNITY = "community", "Suggested by a family"

    PRIVATE = (Status.FAMILY, Status.SUGGESTED)
    PUBLIC = (Status.COMMUNITY, Status.VERIFIED)

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=160)
    description = models.CharField(max_length=500, blank=True)
    category = models.CharField(max_length=16, choices=Category.choices, default=Category.FAMILY_MEETING)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.FAMILY)
    source_type = models.CharField(max_length=12, choices=Source.choices, default=Source.COMMUNITY)
    source_detail = models.CharField(
        max_length=240, blank=True, help_text="Where this came from: a link, a document, or who visited and when.",
    )
    # Set only while the point is private to this family.
    family = models.ForeignKey(
        FamilyCircle, on_delete=models.CASCADE, null=True, blank=True, related_name="meeting_points",
    )
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)
    address = models.CharField(max_length=240, blank=True)
    opening_hours = models.CharField(max_length=120, blank=True)
    contact_phone = models.CharField(max_length=20, blank=True, help_text="A public number only.")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )
    verified_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        indexes = [
            models.Index(fields=["status", "category"]),
            models.Index(fields=["family", "status"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=~Q(status="verified") | ~Q(source_detail=""),
                name="reunification_verified_needs_source",
            ),
            models.CheckConstraint(
                condition=~Q(status__in=["family", "suggested"]) | Q(family__isnull=False),
                name="reunification_private_needs_family",
            ),
            models.CheckConstraint(
                condition=~Q(status__in=["community", "verified"]) | Q(family__isnull=True),
                name="reunification_public_has_no_family",
            ),
        ]

    def __str__(self):
        return self.name

    @property
    def is_official(self):
        return self.status == self.Status.VERIFIED and self.source_type == self.Source.OFFICIAL


class ReunificationPlan(models.Model):
    """How a case's meeting is going. It never changes the case's status."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    case = models.OneToOneField(LostFoundCase, on_delete=models.CASCADE, related_name="reunification_plan")
    meeting_point = models.ForeignKey(
        MeetingPoint, on_delete=models.SET_NULL, null=True, blank=True, related_name="plans",
    )
    selected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )
    selected_at = models.DateTimeField(null=True, blank=True)
    family_arrived_at = models.DateTimeField(null=True, blank=True)
    person_arrived_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=["meeting_point"])]
