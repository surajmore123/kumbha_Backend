# temples/admin.py
from django.contrib import admin
from .models import Temple, TempleAnalyticsView

@admin.register(Temple)
class TempleAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "city",
        "crowd_level",
        "is_active",
        "updated_at",
    )
    list_filter = ("city", "crowd_level", "is_active")
    search_fields = ("name", "city")

    fieldsets = (
        ("Basic Info", {
            "fields": ("name", "description", "image_url")
        }),
        ("Location", {
            "fields": ("latitude", "longitude", "city", "state")
        }),
        ("Crowd Management", {
            "fields": ("crowd_level", "crowd_message")
        }),
        ("System", {
            "fields": ("is_active",)
        }),
    )


@admin.register(TempleAnalyticsView)
class TempleAnalyticsViewAdmin(admin.ModelAdmin):

    list_display = (
        "event_id",
        "temple",
        "user",
        "event_type",
        "created_at",
    )

    list_filter = (
        "event_type",
        "created_at",
    )

    search_fields = (
        "temple__name",
        "user__phone_number",
        "user__email",
    )

    readonly_fields = (
        "event_id",
        "created_at",
    )

    ordering = ("-created_at",)

    autocomplete_fields = ("temple", "user")