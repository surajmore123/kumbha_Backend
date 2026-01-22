from django.db import models
from apps.events.models.BaseModel import BaseModel
from apps.authentication.models import User
from apps.events.models.EventModel import Event
import uuid


class EventAnalytics(models.Model):
    EVENT_TYPE_CHOICES = [
        ("VIEW", "Viewed Event"),
        ("DETAIL_OPEN", "Opened Event Details"),
        ("REMIND_CLICK", "Clicked Reminder"),
    ]

    analytics_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    user = models.ForeignKey(
        "authentication.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="event_analytics",
    )

    event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        related_name="analytics_events",
    )

    event_type = models.CharField(max_length=20, choices=EVENT_TYPE_CHOICES)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "event_analytics"
        indexes = [
            models.Index(fields=["event", "event_type"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        return f"{self.event.event_name} - {self.event_type}"
