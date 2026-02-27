from django.contrib import admin

# crowd/admin.py
from apps.crowd.admin_base import AuditAdmin

from django.contrib import admin

from apps.crowd.models import AppNotification
from .models import (
    Zone,
    ZoneNeighbor,
    ZoneGate,
    UserLocationLog,
    UserZonePresence,
    ZoneCrowdSnapshot,
    Incident
)


@admin.register(Zone)
class ZoneAdmin(AuditAdmin):
    list_display = (
        "name",
        "code",
        "city",
        "capacity",
        "priority",
        "is_active",
        "del_flag",
    )
    search_fields = ("name", "code", "city")
    list_filter = ("city", "is_active", "del_flag")

    # hide from admin form
    exclude = ("user_id_updated_by",)

    def save_model(self, request, obj, form, change):
        obj.user_id_updated_by = request.user
        super().save_model(request, obj, form, change)



@admin.register(ZoneNeighbor)
class ZoneNeighborAdmin(AuditAdmin):
    list_display = ("zone", "neighbor_zone", "distance_meter", "del_flag")
    search_fields = ("zone__name", "neighbor_zone__name")

@admin.register(ZoneGate)
class ZoneGateAdmin(AuditAdmin):
    list_display = (
        "zone",
        "name",
        "gate_type",
        "is_open",
        "del_flag",
    )
    list_filter = ("gate_type", "is_open", "del_flag")
    search_fields = ("zone__name", "name")

@admin.register(Incident)
class IncidentAdmin(AuditAdmin):
    list_display = (
        "title",
        "zone",
        "incident_type",
        "severity",
        "is_active",
        "start_time",
        "end_time",
        "del_flag",
    )
    list_filter = ("incident_type", "severity", "is_active", "del_flag")
    search_fields = ("title", "zone__name")

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)

        if obj.is_active:
            


            AppNotification.objects.create(
                title=obj.title,
                body=obj.description,
                type="ALERT",
                zone=obj.zone,
                severity=obj.severity
            )


@admin.register(AppNotification)
class AppNotificationAdmin(admin.ModelAdmin):
    list_display = ("title", "type", "zone", "severity", "created_at")
    list_filter = ("type", "severity")

@admin.register(UserLocationLog)
class UserLocationLogAdmin(admin.ModelAdmin):
    list_display = ("user", "zone", "recorded_at")
    list_filter = ("zone",)
    search_fields = ("user__username",)
    readonly_fields = [field.name for field in UserLocationLog._meta.fields]

    def has_add_permission(self, request):
        return False
    
    def has_delete_permission(self, request, obj=None):
        return False

    


@admin.register(UserZonePresence)
class UserZonePresenceAdmin(admin.ModelAdmin):
    list_display = ("user", "zone", "entered_at", "exited_at", "is_active")
    list_filter = ("zone", "is_active")
    readonly_fields = [field.name for field in UserZonePresence._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ZoneCrowdSnapshot)
class ZoneCrowdSnapshotAdmin(admin.ModelAdmin):
    list_display = (
        "zone",
        "total_people",
        "occupancy_percent",
        "status",
        "calculated_at",
    )
    list_filter = ("status", "zone")
    readonly_fields = [field.name for field in ZoneCrowdSnapshot._meta.fields]

    def has_add_permission(self, request):
        return False
    
    def has_delete_permission(self, request, obj=None):
        return False




