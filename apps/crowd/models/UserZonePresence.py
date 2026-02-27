from django.db import models
from apps.aiChat.models import BaseModel
from apps.authentication.models import User

class UserZonePresence(BaseModel):
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="zone_presences"
    )

    zone = models.ForeignKey(
        "Zone",
        on_delete=models.CASCADE,
        related_name="current_users"
    )

    entered_at = models.DateTimeField()

    exited_at = models.DateTimeField(blank=True, null=True)

    # where user came from
    previous_zone = models.ForeignKey(
        "Zone",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="next_movements"
    )
    last_seen_at = models.DateTimeField(null=True, blank=True)


    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "user_zone_presence"
        indexes = [
            models.Index(fields=["user"]),
            models.Index(fields=["zone"]),
            models.Index(fields=["is_active"]),
            models.Index(fields=["entered_at"]),
            models.Index(fields=["del_flag"]),
        ]

    def __str__(self):
        return f"{self.user_id} in {self.zone.name}"
