
from django.db import models
from apps.events.models.BaseModel import BaseModel
from apps.authentication.models import User
from apps.events.models.EventModel import Event
from apps.events.models.event_subscription import EventSubscription
import uuid

class ScheduledNotification(BaseModel):
    notification_id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )

    subscription = models.ForeignKey(
        EventSubscription,
        on_delete=models.CASCADE,
        related_name="scheduled_notifications"
    )

    scheduled_at = models.DateTimeField()
    offset_minutes = models.PositiveIntegerField()

    is_sent = models.BooleanField(default=False)
    sent_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "scheduled_notifications"
        indexes = [
            models.Index(fields=["scheduled_at"]),
            models.Index(fields=["is_sent"]),
        ]

    def __str__(self):
        return f"{self.subscription.event.event_name} @ {self.scheduled_at}"