"""
Read-only, for audit and support. Case work happens through the role-checked
API, so nothing here can bypass its rules. No personal details are shown:
descriptions, names, locations, notes and photos stay out of this list.
"""

from django.contrib import admin

from apps.lostfound import models


class _ReadOnly(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(models.LostFoundCase)
class LostFoundCaseAdmin(_ReadOnly):
    list_display = ("reference", "case_type", "status", "reporter_role", "created_at")
    list_filter = ("case_type", "status")
    search_fields = ("reference",)
    fields = ("reference", "case_type", "status", "reporter_role", "created_at", "updated_at", "reunited_at")


@admin.register(models.CaseStatusHistory)
class CaseStatusHistoryAdmin(_ReadOnly):
    list_display = ("case", "from_status", "to_status", "created_at")
    list_filter = ("to_status",)
    fields = ("case", "from_status", "to_status", "created_at")


@admin.register(models.CaseAudit)
class CaseAuditAdmin(_ReadOnly):
    list_display = ("created_at", "action", "case")
    list_filter = ("action",)
    fields = ("created_at", "action", "case", "details")


@admin.register(models.CaseMatch)
class CaseMatchAdmin(_ReadOnly):
    list_display = ("id", "score", "state", "created_at")
    list_filter = ("state",)
    fields = ("id", "score", "state", "created_at", "reviewed_at")


@admin.register(models.CaseNotification)
class CaseNotificationAdmin(_ReadOnly):
    list_display = ("case", "event", "state", "attempts", "created_at", "sent_at")
    list_filter = ("state", "event")
    fields = ("case", "event", "state", "attempts", "created_at", "sent_at")
