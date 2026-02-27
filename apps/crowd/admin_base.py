

from django.contrib import admin


class AuditAdmin(admin.ModelAdmin):
    """
    Automatically stores which admin user updated the record.
    """

    exclude = ("user_id_updated_by",)

    def save_model(self, request, obj, form, change):
        if hasattr(obj, "user_id_updated_by"):
            obj.user_id_updated_by = request.user
        super().save_model(request, obj, form, change)
