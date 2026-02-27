from django.db import models
from apps.aiChat.models import BaseModel

class Incident(BaseModel):
    TRAFFIC = "TRAFFIC"
    CROWD = "CROWD"
    SECURITY = "SECURITY"
    MEDICAL = "MEDICAL"
    INFO = "INFO"

    INCIDENT_TYPES = [
        (TRAFFIC, "Traffic"),
        (CROWD, "Crowd"),
        (SECURITY, "Security"),
        (MEDICAL, "Medical"),
        (INFO, "Information"),
    ]

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"

    SEVERITY_CHOICES = [
        (LOW, "Low"),
        (MEDIUM, "Medium"),
        (HIGH, "High"),
        (CRITICAL, "Critical"),
    ]

    zone = models.ForeignKey(
        "Zone",
        on_delete=models.CASCADE,
        related_name="incidents"
    )

    incident_type = models.CharField(
        max_length=20,
        choices=INCIDENT_TYPES
    )

    severity = models.CharField(
        max_length=10,
        choices=SEVERITY_CHOICES,
        default=LOW
    )

    title = models.CharField(max_length=255)
    description = models.TextField()

    start_time = models.DateTimeField()
    end_time = models.DateTimeField(blank=True, null=True)

    is_active = models.BooleanField(default=True)

    # optional extra data
    latitude = models.DecimalField(max_digits=9, decimal_places=6, blank=True, null=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, blank=True, null=True)

    class Meta:
        db_table = "incidents"
        indexes = [
            models.Index(fields=["zone"]),
            models.Index(fields=["incident_type"]),
            models.Index(fields=["severity"]),
            models.Index(fields=["is_active"]),
            models.Index(fields=["start_time"]),
            models.Index(fields=["del_flag"]),
        ]

    def __str__(self):
        return f"{self.title} - {self.severity}"
