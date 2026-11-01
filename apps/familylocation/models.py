"""
Family location sharing: temporary, chosen by the person, and limited to the
people they pick. It is not tracking.

- Every session ends by itself. An adult can only ever start their own.
- Only the latest position is kept, one row per session. There is no history.
- The moment a session stops or expires, that position is deleted.
- Being reported missing, or a QR scan, changes none of this.
"""

import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone

from apps.family.models import FamilyCircle, FamilyMember


class LocationSession(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Sharing"
        PAUSED = "paused", "Paused"
        STOPPED = "stopped", "Stopped"
        EXPIRED = "expired", "Expired"

    OPEN = (Status.ACTIVE, Status.PAUSED)

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    family = models.ForeignKey(FamilyCircle, on_delete=models.CASCADE, related_name="location_sessions")
    # Whose location this is.
    member = models.ForeignKey(FamilyMember, on_delete=models.CASCADE, related_name="location_sessions")
    # The account that agreed and whose phone reports. For an adult, themselves.
    started_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.ACTIVE)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    paused_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    stale_notified_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["family", "status"]),
            models.Index(fields=["status", "expires_at"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["member"], condition=Q(status__in=["active", "paused"]),
                name="location_one_open_session_per_member",
            ),
            models.UniqueConstraint(
                fields=["started_by"], condition=Q(status__in=["active", "paused"]),
                name="location_one_open_session_per_reporter",
            ),
        ]

    def __str__(self):
        return f"{self.pk} ({self.status})"

    @property
    def is_open(self):
        return self.status in self.OPEN and self.expires_at > timezone.now()

    def recipient_ids(self):
        return list(self.recipients.filter(revoked_at__isnull=True).values_list("member_id", flat=True))


class LocationRecipient(models.Model):
    """One person chosen to see a session. Revoked rows stay as a record."""

    id = models.BigAutoField(primary_key=True)
    session = models.ForeignKey(LocationSession, on_delete=models.CASCADE, related_name="recipients")
    member = models.ForeignKey(FamilyMember, on_delete=models.CASCADE, related_name="location_grants")
    granted_at = models.DateTimeField(auto_now_add=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    last_viewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["session", "member"], name="location_one_grant_per_viewer"),
        ]
        indexes = [models.Index(fields=["member", "revoked_at"])]


class MemberLocation(models.Model):
    """The newest position for a session, and nothing older."""

    session = models.OneToOneField(LocationSession, on_delete=models.CASCADE, primary_key=True, related_name="location")
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)
    accuracy_m = models.FloatField(null=True, blank=True)
    speed_mps = models.FloatField(null=True, blank=True)
    heading = models.FloatField(null=True, blank=True)
    # When the phone took it, which may be well before it arrived here.
    captured_at = models.DateTimeField()
    received_at = models.DateTimeField(auto_now=True)
