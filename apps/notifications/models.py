"""
The personal notification record: what someone was told, whether they've read
it, and how far delivery got. Sending still goes through
`utils.push_notifications`; devices and preferences stay in `apps.authentication`.

Stages are kept apart on purpose. `sent` means the provider accepted a message.
`delivered_at` means the person's app has fetched it. Neither means anyone read
or acted on it.
"""

import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q


class Notification(models.Model):
    class Category(models.TextChoices):
        EMERGENCY = "emergency", "Emergency SOS"
        FAMILY_SAFETY = "family_safety", "Family Safety"
        LOST_FOUND = "lost_found", "Lost & Found"
        SAFETY_QR = "safety_qr", "Digital Safety QR"
        FAMILY_LOCATION = "family_location", "Family Location Sharing"
        REUNIFICATION = "reunification", "Reunification updates"
        OPERATIONS = "operations", "Volunteer operations"
        GENERAL = "general", "General Kumbh updates"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    category = models.CharField(max_length=16, choices=Category.choices)
    title = models.CharField(max_length=160)
    body = models.CharField(max_length=500)
    # Ids and a route only. The server checks access when they're opened.
    data = models.JSONField(default=dict, blank=True)
    # Stops one event reaching one person twice.
    dedupe_key = models.CharField(max_length=120, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "-created_at"]),
            models.Index(fields=["user", "category", "-created_at"]),
            models.Index(fields=["user", "read_at"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "dedupe_key"], condition=~Q(dedupe_key=""), name="notifications_one_per_key",
            ),
        ]


class NotificationDelivery(models.Model):
    """The outbox row for a notification this app sends itself. A failed send
    stays here and is retried by `services.retry_pending`."""

    class State(models.TextChoices):
        PENDING = "pending", "Waiting to send"
        SENT = "sent", "Accepted by the provider"
        NO_DEVICE = "no_device", "No device registered"
        FAILED = "failed", "Gave up"

    MAX_ATTEMPTS = 6

    notification = models.OneToOneField(Notification, on_delete=models.CASCADE, primary_key=True, related_name="delivery")
    push_title = models.CharField(max_length=160)
    push_body = models.CharField(max_length=240)
    # Critical messages ignore preferences. Nothing else may set this.
    critical = models.BooleanField(default=False)
    state = models.CharField(max_length=10, choices=State.choices, default=State.PENDING)
    attempts = models.PositiveSmallIntegerField(default=0)
    next_attempt_at = models.DateTimeField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["state", "next_attempt_at"])]


class NotificationState(models.Model):
    """How far someone has read the shared Kumbh updates, which aren't personal
    records and so can't each be marked."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, primary_key=True, related_name="notification_state",
    )
    general_read_at = models.DateTimeField(null=True, blank=True)
