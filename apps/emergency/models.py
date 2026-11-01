"""
Emergency SOS: a person asking for help through Kumbh Path.

An SOS tells their family and any registered staff. It does not call the police
or an ambulance, and nothing here may say it did.

The statuses mean exactly what they say. FAMILY_NOTIFIED means the notification
provider accepted a message. A family member's acknowledgement is a separate
record and never changes the status. ACKNOWLEDGED and later come only from an
authorized operational user, and nothing resolves a case by itself.
"""

import secrets
import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.family.models import FamilyCircle, FamilyMember
from apps.notifications.models import Notification

_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def new_reference():
    return "SOS-" + "".join(secrets.choice(_ALPHABET) for _ in range(8))


class Status(models.TextChoices):
    CREATED = "CREATED", "Created"
    SUBMITTED = "SUBMITTED", "Submitted"
    FAMILY_NOTIFIED = "FAMILY_NOTIFIED", "Family notified"
    ACKNOWLEDGED = "ACKNOWLEDGED", "Acknowledged by a responder"
    ASSISTANCE_COORDINATED = "ASSISTANCE_COORDINATED", "Assistance coordinated"
    RESOLVED = "RESOLVED", "Resolved"
    CANCELLED = "CANCELLED", "Cancelled"
    CLOSED = "CLOSED", "Closed"


ACTIVE_STATUSES = (
    Status.CREATED, Status.SUBMITTED, Status.FAMILY_NOTIFIED, Status.ACKNOWLEDGED, Status.ASSISTANCE_COORDINATED,
)
_ACTIVE = [s.value for s in ACTIVE_STATUSES]


class EmergencySOS(models.Model):
    class Category(models.TextChoices):
        MEDICAL = "medical", "Medical emergency"
        SEPARATED_VULNERABLE = "separated_vulnerable", "Child or elderly person separated"
        LOST = "lost", "Lost or separated from family"
        SAFETY_THREAT = "safety_threat", "Personal safety threat"
        ACCIDENT = "accident", "Accident or injury"
        CROWD = "crowd", "Crowd-related emergency"
        OTHER = "other", "Other emergency"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    reference = models.CharField(max_length=16, unique=True, default=new_reference, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="emergencies")
    # Made by the app, so a retried request can't create a second SOS.
    client_id = models.UUIDField(editable=False)
    category = models.CharField(max_length=24, choices=Category.choices)
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.CREATED)
    details = models.TextField(max_length=1000, blank=True)
    location_text = models.CharField(max_length=240, blank=True)
    # The latest position the person chose to send. Only ever set by them.
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    accuracy_m = models.FloatField(null=True, blank=True)
    location_at = models.DateTimeField(null=True, blank=True)
    # Set when it was written offline and sent later, so nobody mistakes it for new.
    written_at = models.DateTimeField(null=True, blank=True)
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="assigned_emergencies",
    )
    # From the coordinates. Without one, coordinators still see it, so an SOS
    # with no GPS can't fall between zones.
    zone = models.ForeignKey(
        "crowd.Zone", on_delete=models.SET_NULL, null=True, blank=True, related_name="emergencies",
    )
    cancel_reason = models.CharField(max_length=300, blank=True)
    resolution_note = models.CharField(max_length=500, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "-created_at"]),
            models.Index(fields=["status", "category"]),
            models.Index(fields=["assigned_to", "status"]),
            models.Index(fields=["zone", "status"]),
        ]
        constraints = [
            models.UniqueConstraint(fields=["user", "client_id"], name="emergency_one_sos_per_client_id"),
            models.UniqueConstraint(
                fields=["user"], condition=Q(status__in=_ACTIVE), name="emergency_one_active_sos_per_user",
            ),
        ]

    def __str__(self):
        return self.reference

    @property
    def is_active(self):
        return self.status in ACTIVE_STATUSES


class EmergencyStatusHistory(models.Model):
    """Append-only. `actor` is empty for the system's own steps."""

    class Role(models.TextChoices):
        SYSTEM = "system", "System"
        PERSON = "person", "The person who sent it"
        RESPONDER = "responder", "Authorized responder"

    id = models.BigAutoField(primary_key=True)
    sos = models.ForeignKey(EmergencySOS, on_delete=models.CASCADE, related_name="history")
    from_status = models.CharField(max_length=24, blank=True)
    to_status = models.CharField(max_length=24, choices=Status.choices)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    actor_role = models.CharField(max_length=10, choices=Role.choices)
    reason = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
        indexes = [models.Index(fields=["sos", "created_at"])]


class EmergencyRecipient(models.Model):
    """A family member told about this SOS. `member` is a live link, so someone
    who leaves the family loses access at once."""

    id = models.BigAutoField(primary_key=True)
    sos = models.ForeignKey(EmergencySOS, on_delete=models.CASCADE, related_name="recipients")
    member = models.ForeignKey(FamilyMember, on_delete=models.CASCADE, related_name="emergency_alerts")
    family = models.ForeignKey(FamilyCircle, on_delete=models.CASCADE, related_name="+")
    notification = models.ForeignKey(Notification, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    # This is a relative saying "I've seen this". It is never a responder.
    acknowledged_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["sos", "member"], name="emergency_one_row_per_recipient")]
        indexes = [models.Index(fields=["member"])]


class EmergencyUpdate(models.Model):
    class Kind(models.TextChoices):
        PERSON = "person", "From the person"
        LOCATION = "location", "Location updated"
        RESPONDER = "responder", "Update from a responder"
        INTERNAL = "internal", "Internal note"

    VISIBLE = (Kind.PERSON, Kind.LOCATION, Kind.RESPONDER)

    id = models.BigAutoField(primary_key=True)
    sos = models.ForeignKey(EmergencySOS, on_delete=models.CASCADE, related_name="updates")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    kind = models.CharField(max_length=10, choices=Kind.choices)
    body = models.TextField(max_length=1000, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
        indexes = [models.Index(fields=["sos", "kind"])]


class EmergencyAudit(models.Model):
    """Who did or saw what. Never holds a position or a phone number."""

    id = models.BigAutoField(primary_key=True)
    sos = models.ForeignKey(EmergencySOS, on_delete=models.CASCADE, related_name="audit")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    action = models.CharField(max_length=40)
    details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
