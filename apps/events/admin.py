from django.contrib import admin



from .models import EventRemider,Event,EventAnalytics

from django.contrib import admin
from .models import Event


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = (
        "event_name",
        "event_date",
        "event_category",
        "priority_level",
        "location_type",
        "is_verified",
        "status",
        "show_in_featured",
    )

    list_filter = (
        "event_category",
        "priority_level",
        "location_type",
        "status",
        "is_verified",
        "del_flag",
    )

    search_fields = (
        "event_name",
        "event_subtype",
        "short_description",
        "location_name",
    )

    ordering = ("event_date",)

    readonly_fields = (
        "created_at",
        "updated_at",
        "user_id_updated_by",
    )

    fieldsets = (
        ("Basic Information", {
            "fields": (
                "event_name",
                "event_category",
                "event_subtype",
            )
        }),
        ("Description", {
            "fields": (
                "short_description",
                "description",
            )
        }),
        ("Date & Time", {
            "fields": (
                "event_date",
                "is_all_day",
                "start_time",
                "end_time",
            )
        }),
        ("Location", {
            "fields": (
                "location_type",
                "location_name",
                "latitude",
                "longitude",
            )
        }),
        ("Visibility & Priority", {
            "fields": (
                "priority_level",
                "show_in_app",
                "show_in_featured",
                "status",
            )
        }),
        ("Notifications", {
            "fields": (
                "app_notification_enabled",
                "sms_notification_enabled",
                "notify_days_before",
                "notify_on_event_day",
            )
        }),
        ("Crowd & Safety", {
            "fields": (
                "expected_crowd_level",
                "is_crowd_sensitive",
                "requires_police_advisory",
            )
        }),
        ("Verification", {
            "fields": (
                "data_source",
                "is_verified",
                "verification_notes",
            )
        }),
        ("System Fields", {
            "fields": (
                "del_flag",
                "auto_expire",
                "expiry_date",
                "created_at",
                "updated_at",
                "user_id_updated_by",
            )
        }),
    )



@admin.register(EventRemider)
class EventReminderAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "event",
        "reminder_type",
        "reminder_date",
        "reminder_time",
        "is_active",
    )

    list_filter = (
        "reminder_type",
        "is_active",
        "del_flag",
    )

    search_fields = (
        "user__phone_number",
        "event__event_name",
    )

    readonly_fields = (
        "created_at",
        "updated_at",
        "user_id_updated_by",
    )


@admin.register(EventAnalytics)
class EventAnalyticsAdmin(admin.ModelAdmin):
    list_display = (
        "event",
        "event_type",
        "user",
        "created_at",
    )

    list_filter = (
        "event_type",
        "created_at",
    )

    search_fields = (
        "event__event_name",
        "user__phone_number",
    )

    readonly_fields = ("created_at",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


