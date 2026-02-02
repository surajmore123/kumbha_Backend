
from django.db import models
from apps.events.models.BaseModel import BaseModel
from apps.authentication.models import User
from apps.events.models.EventModel import Event
import uuid


class EventSubscription(BaseModel):
    subscription_id = models.UUIDField(primary_key=True,default=uuid.uuid4,editable=True)

    user = models.ForeignKey(User,on_delete=models.CASCADE,related_name="event_subscriptions")

    event = models.ForeignKey(Event,on_delete=models.CASCADE,related_name="subscriptions")

    is_active = models.BooleanField(default=True)
    reminder_offsets = models.JSONField(default=list,help_text="Minutes before event start")

    class Meta:
     
     db_table = "event_subscriptions"
     unique_together = ("user", "event")
     indexes = [
     models.Index(fields=["user"]),
     models.Index(fields=["event"]),
     models.Index(fields=["is_active"]),
     ]

    def __str__(self):
     
     return f"{self.user_id} → {self.event.event_name}"



        