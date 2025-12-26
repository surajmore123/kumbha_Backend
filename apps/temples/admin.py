# temples/admin.py
from django.contrib import admin
from .models import Temple

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
