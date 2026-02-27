
import uuid
from django.db import models
from apps.aiChat.models import BaseModel
class ZoneNeighbor(BaseModel):
    zone = models.ForeignKey(
        "Zone",
        on_delete=models.CASCADE,
        related_name="neighbors"
    )

    neighbor_zone = models.ForeignKey(
        "Zone",
        on_delete=models.CASCADE,
        related_name="connected_to"
    )

    distance_meter = models.IntegerField(default=0)

    class Meta:
        db_table = "zone_neighbors"
        unique_together = ("zone", "neighbor_zone")
        indexes = [
            models.Index(fields=["zone"]),
            models.Index(fields=["neighbor_zone"]),
            models.Index(fields=["del_flag"]),
        ]

    def __str__(self):
        return f"{self.zone.name} → {self.neighbor_zone.name}"
