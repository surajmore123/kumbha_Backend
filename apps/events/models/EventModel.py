

from apps.aiChat.models import BaseModel
from django.db import models
import uuid
from django.utils import timezone   


class Event(BaseModel):
    EVENT_CATEGORY_CHOICES = [
        ("KUMBH_LIFECYCLE", "Kumbh Lifecycle"),
        ("SNAN", "Snan"),
        ("AUSPICIOUS", "Auspicious Date"),
    ]

    PRIORITY_CHOICES = [
        ("HIGH", "High"),
        ("NORMAL", "Normal"),
        ("LOW", "Low"),
    ]

    LOCATION_TYPE_CHOICES = [
        ("NASHIK", "Nashik"),
        ("TRIMBAKESHWAR", "Trimbakeshwar"),
        ("BOTH", "Both"),
        ("NOT_APPLICABLE", "Not Applicable"),
    ]

    CROWD_LEVEL_CHOICES = [
        ("LOW", "Low"),
        ("MEDIUM", "Medium"),
        ("HIGH", "High"),
        ("VERY_HIGH", "Very High"),
    ]

    DATA_SOURCE_CHOICES = [
        ("GOVT", "Government"),
        ("TEMPLE_TRUST", "Temple Trust"),
        ("ASTRO_PANEL", "Astrologer Panel"),
        ("MANUAL", "Manual Verified"),
    ]

    STATUS_CHOICES = [
        ("DRAFT", "Draft"),
        ("PUBLISHED", "Published"),
        ("ARCHIVED", "Archived"),
    ]

    event_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Basic Info
    event_name = models.CharField(max_length=255)
    short_description = models.CharField(max_length=300,null=True,blank=True,help_text="Short summary shown in lists, cards, and notifications")
    description = models.TextField(
        null=True,
    blank=True,
    help_text="Detailed description shown on event detail screen"
    )
    event_category = models.CharField(max_length=20, choices=EVENT_CATEGORY_CHOICES)
    event_subtype = models.CharField(max_length=100)

    # Date & Time
    event_date = models.DateField()
    start_time = models.TimeField(null=True, blank=True)
    end_time = models.TimeField(null=True, blank=True)
    is_all_day = models.BooleanField(default=True)

    # Location
    location_type = models.CharField(max_length=20, choices=LOCATION_TYPE_CHOICES)
    location_name = models.CharField(max_length=255, null=True, blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)

    # Visibility & Priority
    priority_level = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default="NORMAL")
    show_in_app = models.BooleanField(default=True)
    show_in_featured = models.BooleanField(default=False)

    # Notifications
    app_notification_enabled = models.BooleanField(default=True)
    sms_notification_enabled = models.BooleanField(default=False)
    notify_days_before = models.PositiveSmallIntegerField(null=True, blank=True)
    notify_on_event_day = models.BooleanField(default=True)

    # Crowd & Safety
    expected_crowd_level = models.CharField(
        max_length=10, choices=CROWD_LEVEL_CHOICES, null=True, blank=True
    )
    is_crowd_sensitive = models.BooleanField(default=False)
    requires_police_advisory = models.BooleanField(default=False)

    # Verification
    data_source = models.CharField(max_length=20, choices=DATA_SOURCE_CHOICES)
    is_verified = models.BooleanField(default=False)
    verification_notes = models.TextField(null=True, blank=True)

    # Lifecycle
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="DRAFT")
    auto_expire = models.BooleanField(default=True)
    expiry_date = models.DateField(null=True, blank=True)

    class Meta:
        db_table = "events"
        indexes = [
            models.Index(fields=["event_date"]),
            models.Index(fields=["event_category"]),
            models.Index(fields=["priority_level"]),
        ]

    def __str__(self):
        return f"{self.event_name} ({self.event_date})"