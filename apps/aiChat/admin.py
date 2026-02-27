from django.contrib import admin
from .models import ChatSession, ChatMessage


@admin.register(ChatSession)
class ChatSessionAdmin(admin.ModelAdmin):
    readonly_fields = ("created_at", "updated_at", "last_login")
    list_display = (
        "session_id",
        "user",
        "title",
        "mode",
        "last_message_at",
        "created_at",
        "updated_at",
        "del_flag",
        "user_id_updated_by",
    )
    list_filter = ("mode", "del_flag", "created_at")
    search_fields = (
        "session_id",
        "title",
        "user__phone_number",
        "user__email",
    )
    readonly_fields = ("created_at", "updated_at")

    # ordering in admin list view
    ordering = ("-created_at",)

    # Show foreign key dropdowns nicely
    autocomplete_fields = ("user", "user_id_updated_by")


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    
    list_display = (
        "message_id",
        "session",
        "user",
        "role",
        "message_type",
        "short_content",
        "created_at",
        "del_flag",
        "user_id_updated_by",
    )
    list_filter = ("role", "message_type", "del_flag", "created_at")
    search_fields = (
        "message_id",
        "content",
        "session__session_id",
        "user__phone_number",
        "user__email",
    )
    readonly_fields = ("created_at",)

    ordering = ("-created_at",)

    autocomplete_fields = ("session", "user", "user_id_updated_by")
    

    def short_content(self, obj):
        content = obj.content or ""
        return content[:40] + ("..." if len(content) > 40 else "")
    
    
    short_content.short_description = "Content"
