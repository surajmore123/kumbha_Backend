from django.contrib import admin

from .models import Announcement, Enquiry, Listing, Partner, SafetyCard, UserItem, WaitlistEntry


@admin.register(Listing)
class ListingAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "town", "price_from", "status", "partner")
    list_filter = ("category", "status", "town", "trust")
    search_fields = ("name", "area", "type")


@admin.register(Partner)
class PartnerAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "town", "contact_phone", "status", "created_at")
    list_filter = ("status", "category")
    search_fields = ("name", "contact_phone", "registration_number")


@admin.register(Enquiry)
class EnquiryAdmin(admin.ModelAdmin):
    list_display = ("subject", "name", "phone", "people", "status", "created_at")
    list_filter = ("status", "language")
    search_fields = ("subject", "name", "phone")


@admin.register(Announcement)
class AnnouncementAdmin(admin.ModelAdmin):
    list_display = ("title", "kind", "pinned", "published", "starts_on", "ends_on")
    list_filter = ("kind", "published", "pinned")


@admin.register(WaitlistEntry)
class WaitlistAdmin(admin.ModelAdmin):
    list_display = ("name", "contact", "language", "created_at")


# Personal data: counts are visible to staff, contents only by opening a row.
admin.site.register(SafetyCard)
admin.site.register(UserItem)
