from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.translation import gettext_lazy as _

from .models import User, Otp


class UserAdmin(BaseUserAdmin):
    """Admin config for custom User model with phone_number as username."""
    model = User
    readonly_fields = ("created_at", "updated_at", "last_login")

    # columns in list view
    list_display = (
        "phone_number",
        "email",
        "full_Name",
        "otp_verified",
        "is_staff",
        "is_active",
    )
    list_filter = ("is_staff", "is_superuser", "is_active", "otp_verified")

    # which field is used as the identifier
    ordering = ("phone_number",)
    search_fields = ("phone_number", "email", "full_Name")

    # fields shown on the user change page
    
    fieldsets = (
        (None, {"fields": ("phone_number", "password")}),
        (_("Personal info"), {"fields": ("full_Name", "email", "profile_pic_url")}),
        (
            _("Permissions"),
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "otp_verified",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        (_("Important dates"), {"fields": ("last_login", "created_at", "updated_at")}),
    )

    # fields used when creating a user from admin "Add user" page
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "phone_number",
                    "email",
                    "full_Name",
                    "password1",
                    "password2",
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "otp_verified",
                ),
            },
        ),
    )


@admin.register(Otp)
class OtpAdmin(admin.ModelAdmin):
    list_display = ("otp_id", "user", "otp_code", "is_used", "is_del", "expiry_time")
    list_filter = ("is_used", "is_del")
    search_fields = ("user__phone_number", "user__email", "otp_code")
    readonly_fields = ("created_at", "updated_at")


# register custom User admin
admin.site.register(User, UserAdmin)
