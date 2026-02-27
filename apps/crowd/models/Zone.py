# crowd/models.py

import uuid
from django.db import models
from apps.aiChat.models import BaseModel


class Zone(BaseModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # stable reference used in integrations
    code = models.CharField(max_length=50, unique=True)

    # display name
    name = models.CharField(max_length=255)

    description = models.TextField(blank=True, null=True)

    city = models.CharField(max_length=120)

    # center coordinates
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)

    # optional circular boundary
    radius_m = models.IntegerField(blank=True, null=True)

    # polygon for future GIS upgrades
    polygon = models.JSONField(blank=True, null=True)

    # expected allowed people
    capacity = models.IntegerField(default=0)

    # importance ranking
    priority = models.IntegerField(default=0)

    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "zones"
        indexes = [
            models.Index(fields=["code"]),
            models.Index(fields=["city"]),
            models.Index(fields=["is_active"]),
            models.Index(fields=["del_flag"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.code})"
