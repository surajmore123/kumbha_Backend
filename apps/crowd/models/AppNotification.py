from django.db import models
from apps.aiChat.models import BaseModel
from .Zone import Zone
class AppNotification(BaseModel):

    TYPE_CHOICES = (
        ("ALERT", "Alert"),
        ("MESSAGE", "Message"),
    )

    title = models.CharField(max_length=255)
    body = models.TextField()

    type = models.CharField(
        max_length=10,
        choices=TYPE_CHOICES,
    )

    zone = models.ForeignKey(
        Zone,
        null=True,
        blank=True,
        on_delete=models.SET_NULL
    )

    severity = models.CharField(
        max_length=20,
        null=True,
        blank=True
    )

    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "app_notifications"
        indexes = [
            models.Index(fields=["type"]),
            models.Index(fields=["created_at"]),
            models.Index(fields=["is_active"]),
        ]