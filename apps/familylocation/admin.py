"""
Read-only, and deliberately without positions: `MemberLocation` isn't registered,
so nobody can see where a family member is from the admin.
"""

from django.contrib import admin

from apps.familylocation import models


@admin.register(models.LocationSession)
class LocationSessionAdmin(admin.ModelAdmin):
    list_display = ("id", "status", "created_at", "expires_at", "ended_at")
    list_filter = ("status",)
    fields = ("id", "status", "created_at", "expires_at", "ended_at")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
