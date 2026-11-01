"""
Digital Safety QR.

A QR holds only a random token inside a URL. The token is never stored: each
identity keeps a random salt, the token is derived from it with a server key,
and only the token's hash is kept for lookups. So guardians on different phones
can see the same QR, while a copy of the database alone yields no working token.

A scan identifies a card, not a person, and proves nothing about who a guardian
is. Nobody is marked missing by a scan: a helper has to confirm what they see.
"""

import base64
import hashlib
import hmac
import secrets
import uuid
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone

from apps.family.models import FamilyCircle, FamilyMember

# After "#" so the token never reaches a server if an ordinary camera opens it.
QR_PAYLOAD_BASE = "https://kumbhapath.in/safety/qr"
_REFERENCE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def new_salt():
    return secrets.token_hex(32)


def derive_token(salt):
    key = settings.SAFETY_QR_SECRET.encode("utf-8")
    digest = hmac.new(key, f"safety-qr:{salt}".encode("utf-8"), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def hash_token(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def new_reference():
    return "KP-" + "".join(secrets.choice(_REFERENCE_ALPHABET) for _ in range(8))


class SafetyHelper(models.Model):
    """Someone allowed to scan. Granted only by an admin after checking them,
    never by the app. The Safety Operations Dashboard will manage these later."""

    class Role(models.TextChoices):
        VOLUNTEER = "volunteer", "Volunteer"
        HELP_DESK = "help_desk", "Help desk operator"
        SAFETY_STAFF = "safety_staff", "Safety coordinator"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        ACTIVE = "active", "Active"
        SUSPENDED = "suspended", "Suspended"
        DEACTIVATED = "deactivated", "Deactivated"

    class Availability(models.TextChoices):
        AVAILABLE = "AVAILABLE", "Available"
        BUSY = "BUSY", "Busy"
        OFF_DUTY = "OFF_DUTY", "Off duty"
        UNAVAILABLE = "UNAVAILABLE", "Unavailable"

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="safety_helper")
    role = models.CharField(max_length=12, choices=Role.choices)
    is_active = models.BooleanField(default=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.ACTIVE)
    zones = models.ManyToManyField("crowd.Zone", blank=True, related_name="helpers")
    # Never grants anything. It only says whether someone can take new work.
    availability = models.CharField(max_length=12, choices=Availability.choices, default=Availability.AVAILABLE)
    availability_updated_at = models.DateTimeField(null=True, blank=True)
    setup_code_hash = models.CharField(max_length=128, blank=True, editable=False)
    setup_expires_at = models.DateTimeField(null=True, blank=True, editable=False)
    credential_set_at = models.DateTimeField(null=True, blank=True, editable=False)
    expires_at = models.DateTimeField(null=True, blank=True, help_text="Leave empty for no end date.")
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.pk} ({self.role})"

    @property
    def is_current(self):
        return (
            self.is_active and self.status == self.Status.ACTIVE
            and (self.expires_at is None or self.expires_at > timezone.now())
        )

    @classmethod
    def current_for(cls, user):
        helper = cls.objects.filter(user=user).first()
        return helper if helper and helper.is_current else None


class SafetyQRIdentity(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        REVOKED = "revoked", "Revoked"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    member = models.ForeignKey(FamilyMember, on_delete=models.CASCADE, related_name="safety_qrs")
    salt = models.CharField(max_length=64, default=new_salt, editable=False)
    token_hash = models.CharField(max_length=64, unique=True, editable=False)
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.ACTIVE)
    expires_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    revoked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )
    last_scanned_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["member", "status"])]
        constraints = [
            models.UniqueConstraint(
                fields=["member"], condition=Q(status="active"), name="safety_one_active_qr_per_member",
            ),
        ]

    def __str__(self):
        return f"{self.pk} ({self.status})"

    def save(self, *args, **kwargs):
        if not self.token_hash:
            self.token_hash = hash_token(derive_token(self.salt))
        super().save(*args, **kwargs)

    @property
    def is_usable(self):
        return self.status == self.Status.ACTIVE and (
            self.expires_at is None or self.expires_at > timezone.now()
        )

    @property
    def token(self):
        """Derived on demand. None if the server key has changed since."""
        token = derive_token(self.salt)
        return token if hmac.compare_digest(hash_token(token), self.token_hash) else None

    @property
    def payload(self):
        token = self.token
        return f"{QR_PAYLOAD_BASE}#t={token}" if token else None

    def revoke(self, by):
        self.status = self.Status.REVOKED
        self.revoked_at = timezone.now()
        self.revoked_by = by
        self.save(update_fields=["status", "revoked_at", "revoked_by"])


class SafetyAlert(models.Model):
    """Something a helper confirmed in person. Never created by a scan alone,
    and "separated" means only that: it doesn't mark anyone as missing."""

    class Kind(models.TextChoices):
        SEPARATED = "separated", "Separated from family"
        MEDICAL = "medical", "Medical assistance required"
        OTHER = "other", "Other assistance required"

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        ACKNOWLEDGED = "acknowledged", "Acknowledged by family"
        RESOLVED = "resolved", "Resolved"

    class Delivery(models.TextChoices):
        PENDING = "pending", "Not attempted yet"
        SENT = "sent", "Sent to at least one device"
        NO_DEVICES = "no_devices", "No family device registered"
        UNAVAILABLE = "unavailable", "Notification service unavailable"

    OPEN_STATUSES = (Status.OPEN, Status.ACKNOWLEDGED)

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    reference = models.CharField(max_length=16, unique=True, default=new_reference, editable=False)
    family = models.ForeignKey(FamilyCircle, on_delete=models.CASCADE, related_name="safety_alerts")
    member = models.ForeignKey(FamilyMember, on_delete=models.CASCADE, related_name="safety_alerts")
    identity = models.ForeignKey(SafetyQRIdentity, on_delete=models.SET_NULL, null=True, related_name="alerts")
    kind = models.CharField(max_length=10, choices=Kind.choices)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.OPEN)
    helper = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="safety_alerts_raised",
    )
    helper_role = models.CharField(max_length=12, choices=SafetyHelper.Role.choices)
    note = models.CharField(max_length=200, blank=True, help_text="Written by the helper for the family.")
    # The helper's position, recorded only if they allowed location access.
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    delivery = models.CharField(max_length=12, choices=Delivery.choices, default=Delivery.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    acknowledged_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["family", "status"])]
        constraints = [
            models.UniqueConstraint(
                fields=["member", "kind"], condition=Q(status__in=["open", "acknowledged"]),
                name="safety_one_open_alert_per_member_kind",
            ),
            models.CheckConstraint(
                condition=(
                    Q(latitude__isnull=True, longitude__isnull=True)
                    | Q(latitude__isnull=False, longitude__isnull=False)
                ),
                name="safety_alert_location_is_complete",
            ),
        ]

    def __str__(self):
        return self.reference


class SafetyScanLog(models.Model):
    """Every scan attempt. Holds no token or personal detail. Its id is the
    short-lived proof a helper needs to confirm what they found."""

    class Outcome(models.TextChoices):
        RESOLVED = "resolved", "Resolved"
        UNKNOWN = "unknown", "Unknown code"
        REVOKED = "revoked", "Revoked or expired"
        DENIED = "denied", "Not an authorized helper"

    VALID_FOR = timedelta(minutes=15)

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    identity = models.ForeignKey(SafetyQRIdentity, on_delete=models.SET_NULL, null=True, related_name="scans")
    outcome = models.CharField(max_length=8, choices=Outcome.choices)
    situation = models.CharField(max_length=12, blank=True)
    alert = models.ForeignKey(SafetyAlert, on_delete=models.SET_NULL, null=True, blank=True, related_name="scans")
    confirmed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.outcome} {self.created_at:%Y-%m-%d %H:%M}"

    @property
    def is_fresh(self):
        return timezone.now() - self.created_at <= self.VALID_FOR
