from django.db import models
from apps.aiChat.models import BaseModel


from apps.authentication.models import User


class UserLocationLog(BaseModel):
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="location_logs"
    )

    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)


    accuracy_m = models.FloatField(blank=True, null=True)

    # speed from device (m/s)
    speed = models.FloatField(blank=True, null=True)

    # which zone system mapped it to (filled by backend)
    zone = models.ForeignKey(
        "Zone",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="user_locations"
    )

    recorded_at = models.DateTimeField()

    class Meta:
        db_table = "user_location_logs"
        indexes = [
            models.Index(fields=["user"]),
            models.Index(fields=["zone"]),
            models.Index(fields=["recorded_at"]),
            models.Index(fields=["del_flag"]),
        ]

    def __str__(self):
        return f"{self.user_id} @ {self.recorded_at}"
