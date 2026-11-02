"""
Where staff manage meeting points. Marking one verified needs a named source and
records who did it. Plans aren't here: they belong to the case.
"""

from django.contrib import admin, messages

from apps.reunification import services
from apps.reunification.models import MeetingPoint


@admin.register(MeetingPoint)
class MeetingPointAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "status", "source_type", "verified_by", "verified_at")
    list_filter = ("status", "category", "source_type")
    search_fields = ("name", "source_detail")
    exclude = ("family", "created_by")
    readonly_fields = ("verified_by", "verified_at")
    actions = ("mark_verified", "mark_community", "retire")

    def save_model(self, request, obj, form, change):
        if obj.status == MeetingPoint.Status.VERIFIED and not obj.verified_by_id:
            try:
                services.review_point(
                    obj, request.user, MeetingPoint.Status.VERIFIED,
                    source_type=obj.source_type, source_detail=obj.source_detail,
                )
            except services.ReunionError as problem:
                obj.status = MeetingPoint.Status.COMMUNITY
                obj.save()
                self.message_user(request, f"Kept unverified: {problem.message}", messages.ERROR)
            return
        super().save_model(request, obj, form, change)

    def _review(self, request, queryset, decision):
        done = 0
        for point in queryset:
            try:
                services.review_point(point, request.user, decision)
                done += 1
            except services.ReunionError as problem:
                self.message_user(request, f"{point.name}: {problem.message}", messages.ERROR)
        self.message_user(request, f"{done} updated.")

    @admin.action(description="Mark verified (needs a source on each point)")
    def mark_verified(self, request, queryset):
        self._review(request, queryset, MeetingPoint.Status.VERIFIED)

    @admin.action(description="Allow as a community suggestion (not verified)")
    def mark_community(self, request, queryset):
        self._review(request, queryset, MeetingPoint.Status.COMMUNITY)

    @admin.action(description="Retire")
    def retire(self, request, queryset):
        self._review(request, queryset, MeetingPoint.Status.RETIRED)
