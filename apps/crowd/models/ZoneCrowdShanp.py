from django.db import models
from apps.aiChat.models import BaseModel

class ZoneCrowdSnapshot(BaseModel):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"
    CLOSED = "CLOSED"

    STATUS_CHOICES = [
        (LOW, "Low"),
        (MEDIUM, "Medium"),
        (HIGH, "High"),
        (CRITICAL, "Critical"),
        (CLOSED, "Closed"),
    ]

    zone = models.ForeignKey(
        "Zone",
        on_delete=models.CASCADE,
        related_name="crowd_snapshots"
    )

    total_people = models.IntegerField(default=0)

    occupancy_percent = models.FloatField(default=0)

    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default=LOW
    )

    # optional debug / intelligence data
    avg_speed = models.FloatField(blank=True, null=True)
    incident_count = models.IntegerField(default=0)

    calculated_at = models.DateTimeField()

    class Meta:
        db_table = "zone_crowd_snapshots"
        indexes = [
            models.Index(fields=["zone"]),
            models.Index(fields=["status"]),
            models.Index(fields=["calculated_at"]),
            models.Index(fields=["del_flag"]),
        ]

    def __str__(self):
        return f"{self.zone.name} - {self.status}"
