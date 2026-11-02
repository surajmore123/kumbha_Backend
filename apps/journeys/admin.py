from django.contrib import admin

from apps.journeys.models import JourneyPlan


@admin.register(JourneyPlan)
class JourneyPlanAdmin(admin.ModelAdmin):
    # Plans are personal: support staff see the summary, not notes.
    list_display = ("title", "status", "arrival_date", "departure_date", "created_at")
    list_filter = ("status",)
    readonly_fields = ("user", "created_at", "updated_at")
    exclude = ("notes", "accessibility_notes", "dietary_notes")
