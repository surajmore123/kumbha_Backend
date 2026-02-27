from django.db import models
from apps.aiChat.models import BaseModel

class ZoneGate(BaseModel):
    ENTRY = "ENTRY"
    EXIT = "EXIT"
    BOTH = "BOTH"

    GATE_TYPES = [
        (ENTRY, "Entry"),
        (EXIT, "Exit"),
        (BOTH, "Both"),
    ]

    zone = models.ForeignKey(
        "Zone",
        on_delete=models.CASCADE,
        related_name="gates"
    )

    name = models.CharField(max_length=120)

    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)

    gate_type = models.CharField(max_length=10, choices=GATE_TYPES, default=BOTH)

    is_open = models.BooleanField(default=True)

    class Meta:
        db_table = "zone_gates"
        indexes = [
            models.Index(fields=["zone"]),
            models.Index(fields=["gate_type"]),
            models.Index(fields=["is_open"]),
            models.Index(fields=["del_flag"]),
        ]

    def __str__(self):
        return f"{self.zone.name} - {self.name}"
