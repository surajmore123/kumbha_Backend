"""
Read-only views for support and audit. Names, numbers and birth dates aren't
shown, photos and emergency contacts aren't registered at all, and invitation
codes can't be seen because only their hashes exist.
"""

from django.contrib import admin

from apps.family import models


class _ReadOnly(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class MemberInline(admin.TabularInline):
    model = models.FamilyMember
    fields = ("id", "kind", "role", "relationship", "created_at")
    readonly_fields = fields
    extra = 0
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(models.FamilyCircle)
class FamilyCircleAdmin(_ReadOnly):
    list_display = ("id", "name", "language", "member_total", "created_at")
    search_fields = ("id", "name")
    fields = ("id", "name", "language", "created_at", "updated_at")
    inlines = [MemberInline]

    @admin.display(description="Members")
    def member_total(self, obj):
        return obj.members.count()


@admin.register(models.FamilyMember)
class FamilyMemberAdmin(_ReadOnly):
    list_display = ("id", "family", "kind", "role", "relationship", "created_at")
    list_filter = ("kind", "role")
    fields = ("id", "family", "kind", "role", "relationship", "language", "created_at")
    list_select_related = ("family",)


@admin.register(models.GuardianLink)
class GuardianLinkAdmin(_ReadOnly):
    list_display = ("dependent", "guardian", "created_at")


@admin.register(models.FamilyInvitation)
class FamilyInvitationAdmin(_ReadOnly):
    list_display = ("id", "family", "status", "expires_at", "created_at", "responded_at")
    list_filter = ("status",)
    fields = ("id", "family", "relationship", "status", "expires_at", "created_at", "responded_at")
    list_select_related = ("family",)


@admin.register(models.FamilyAuditLog)
class FamilyAuditLogAdmin(_ReadOnly):
    list_display = ("created_at", "action", "family_ref", "target_member")
    list_filter = ("action",)
    search_fields = ("family_ref",)
    date_hierarchy = "created_at"
