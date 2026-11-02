"""
Read-only, and deliberately without details or positions. Responders work
through the role-checked operations API, not the admin.
"""

from django.contrib import admin

from apps.emergency import models


@admin.register(models.EmergencySOS)
class EmergencySOSAdmin(admin.ModelAdmin):
    list_display = ("reference", "category", "status", "created_at", "updated_at")
    list_filter = ("status", "category")
    search_fields = ("reference",)
    fields = ("reference", "category", "status", "created_at", "updated_at")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
