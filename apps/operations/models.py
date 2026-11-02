"""
Who is working which case, and a record of what administrators and operators did.

Roles, zones and availability stay on `apps.safety.SafetyHelper`, and cases stay
in `apps.lostfound`. `LostFoundCase.assigned_to` remains the current assignee;
this adds the history and working status that field can't hold.
"""

import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.lostfound.models import LostFoundCase


class CaseAssignment(models.Model):
    class Status(models.TextChoices):
        ASSIGNED = "ASSIGNED", "Assigned"
        ACCEPTED = "ACCEPTED", "Accepted"
        IN_PROGRESS = "IN_PROGRESS", "In progress"
        ESCALATED = "ESCALATED", "Escalated"
        COMPLETED = "COMPLETED", "Completed"
        REASSIGNED = "REASSIGNED", "Reassigned"

    OPEN = (Status.ASSIGNED, Status.ACCEPTED, Status.IN_PROGRESS, Status.ESCALATED)
    _OPEN = [s.value for s in OPEN]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    case = models.ForeignKey(LostFoundCase, on_delete=models.CASCADE, related_name="assignments")
    volunteer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="case_assignments")
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.ASSIGNED)
    notes = models.CharField(max_length=500, blank=True)
    escalation_reason = models.CharField(max_length=500, blank=True)
    assigned_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-assigned_at"]
        indexes = [
            models.Index(fields=["volunteer", "status"]),
            models.Index(fields=["case", "-assigned_at"]),
            models.Index(fields=["status"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["case"], condition=Q(status__in=["ASSIGNED", "ACCEPTED", "IN_PROGRESS", "ESCALATED"]),
                name="operations_one_open_assignment_per_case",
            ),
        ]

    def __str__(self):
        return f"{self.pk} ({self.status})"

    @property
    def is_open(self):
        return self.status in self.OPEN


class OperationsAudit(models.Model):
    """Account and access changes. Never holds a credential, phone number or
    position. Case and SOS events stay in their own audit tables."""

    id = models.BigAutoField(primary_key=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    target = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    action = models.CharField(max_length=40)
    details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["target", "-created_at"]), models.Index(fields=["action"])]
