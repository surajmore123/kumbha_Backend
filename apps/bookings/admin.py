"""Editors verify stays here. Saved bookings are private and aren't listed."""

from django.contrib import admin, messages
from django.utils import timezone

from apps.bookings import models
from apps.website.models import ListingStatus


class StayTextInline(admin.StackedInline):
    model = models.StayText
    extra = 0
    max_num = 3


class StayRoomInline(admin.TabularInline):
    model = models.StayRoom
    extra = 0


class StayImageInline(admin.TabularInline):
    model = models.StayImage
    extra = 0


@admin.register(models.StayArea)
class StayAreaAdmin(admin.ModelAdmin):
    list_display = ("name", "position", "latitude", "longitude")
    list_editable = ("position",)


@admin.register(models.Amenity)
class AmenityAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "position")
    list_editable = ("position",)


@admin.register(models.StayProfile)
class StayProfileAdmin(admin.ModelAdmin):
    list_display = (
        "__str__", "stay_type", "area", "listing_status", "verification_status",
        "price_status", "last_verified_on", "expires_on",
    )
    list_filter = ("verification_status", "stay_type", "area", "price_status", "listing__status")
    search_fields = ("listing__name", "address")
    autocomplete_fields = ()
    raw_id_fields = ("listing",)
    filter_horizontal = ("amenities", "sources")
    inlines = [StayTextInline, StayRoomInline, StayImageInline]
    actions = ["mark_verified", "mark_expired", "publish", "unpublish"]
    list_select_related = ("listing", "area")

    @admin.display(description="Listing")
    def listing_status(self, obj):
        return obj.listing.status

    @admin.action(description="Mark verified today")
    def mark_verified(self, request, queryset):
        queryset.update(verification_status="verified", last_verified_on=timezone.localdate())

    @admin.action(description="Mark expired (hides from the app)")
    def mark_expired(self, request, queryset):
        queryset.update(verification_status="expired")

    @admin.action(description="Publish listing (verified stays only)")
    def publish(self, request, queryset):
        for stay in queryset.select_related("listing"):
            if stay.verification_status != "verified":
                self.message_user(request, f"{stay} isn't verified, so it stays unpublished.", messages.ERROR)
                continue
            stay.listing.status = ListingStatus.published
            stay.listing.save(update_fields=["status", "updated_at"])

    @admin.action(description="Unpublish listing")
    def unpublish(self, request, queryset):
        for stay in queryset.select_related("listing"):
            stay.listing.status = ListingStatus.draft
            stay.listing.save(update_fields=["status", "updated_at"])


@admin.register(models.TransportProvider)
class TransportProviderAdmin(admin.ModelAdmin):
    list_display = ("name", "mode", "is_official", "integration", "can_book", "is_active", "last_verified_on")
    list_filter = ("mode", "is_official", "integration", "is_active")
    search_fields = ("name",)
