"""
Helpers are the one thing edited here: an admin grants scanning after checking
the person. Everything else is read-only. Salts, hashes, notes and locations
aren't shown.
"""

from django.contrib import admin

from apps.safety import models


class _ReadOnly(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(models.SafetyHelper)
class SafetyHelperAdmin(admin.ModelAdmin):
    list_display = ("user", "role", "is_active", "expires_at", "created_at")
    list_filter = ("role", "is_active")
    raw_id_fields = ("user",)
    readonly_fields = ("approved_by", "created_at")

    def save_model(self, request, obj, form, change):
        if not change:
            obj.approved_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(models.SafetyQRIdentity)
class SafetyQRIdentityAdmin(_ReadOnly):
    list_display = ("id", "status", "created_at", "revoked_at", "last_scanned_at")
    list_filter = ("status",)
    fields = ("id", "status", "expires_at", "created_at", "revoked_at", "last_scanned_at")


@admin.register(models.SafetyAlert)
class SafetyAlertAdmin(_ReadOnly):
    list_display = ("reference", "kind", "status", "delivery", "helper_role", "created_at")
    list_filter = ("status", "kind", "delivery")
    search_fields = ("reference",)
    fields = (
        "reference", "kind", "status", "delivery", "helper_role", "created_at", "acknowledged_at", "resolved_at",
    )


@admin.register(models.SafetyScanLog)
class SafetyScanLogAdmin(_ReadOnly):
    list_display = ("created_at", "outcome", "situation", "confirmed_at")
    list_filter = ("outcome", "situation")
    date_hierarchy = "created_at"
    fields = ("id", "outcome", "situation", "created_at", "confirmed_at")
