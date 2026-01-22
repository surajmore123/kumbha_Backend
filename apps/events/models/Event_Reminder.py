
from django.db import models
from apps.events.models.BaseModel import BaseModel
from apps.authentication.models import User
from apps.events.models.EventModel import Event

import uuid

class EventRemider(BaseModel):
    REMINDER_TYPE_CHOICES = [
        ("APP", "App Notification"),
        ("SMS", "SMS"),
    ]

    reminder_id = models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="event_reminders",
    )
    
    event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        related_name="user_reminders",
    )

    reminder_type = models.CharField(max_length=10, choices=REMINDER_TYPE_CHOICES)
    reminder_date = models.DateField(null=True, blank=True)
    reminder_time = models.TimeField(null=True, blank=True)

    is_active = models.BooleanField(default=True)


    class Meta:
        db_table = "event_reminders"
        unique_together = ("user", "event", "reminder_type")
        indexes = [
            models.Index(fields=["event"]),
            models.Index(fields=["user"]),
        ]

    def __str__(self):
        return f"Reminder: {self.user.phone_number} → {self.event.event_name}"

