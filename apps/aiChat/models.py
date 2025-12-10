

import uuid
from django.db import models
from django.conf import settings

from django.db import models

from apps.authentication.models import User



class BaseModel(models.Model):
    """
    Common base model used across all tables.
    Contains:
    - del_flag (soft delete)
    - created_at
    - updated_at
    - user_id_updated_by
    """

    del_flag = models.SmallIntegerField(default=0, help_text="Soft delete flag")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    user_id_updated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="updated_%(class)s_records"
    )

    class Meta:
        abstract = True



class ChatSession(BaseModel):
    session_id = models.UUIDField(
        primary_key=True, default=uuid.uuid4, editable=False
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="chat_sessions",
    )
    title = models.CharField(max_length=255, blank=True, null=True)
    mode = models.CharField(max_length=50, default="guru_ai")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_message_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = "chat_sessions"

    def __str__(self):
        return f"{self.user.phone_number} - {self.title or self.session_id}"
    
    

class ChatMessage(BaseModel):
    ROLE_CHOICES = [
        ("user", "User"),
        ("assistant", "Assistant"),
        ("system", "System"),
    ]

    MESSAGE_TYPES = [
        ("text", "Text"),
        ("image", "Image"),
        ("audio", "Audio"),
        ("file", "File"),
    ]

    message_id = models.BigAutoField(primary_key=True)
    session = models.ForeignKey(ChatSession, on_delete=models.CASCADE, related_name="messages")
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    
    role = models.CharField(max_length=10, choices=ROLE_CHOICES)
    message_type = models.CharField(max_length=20, choices=MESSAGE_TYPES, default="text")

    # Stores text if message_type='text'
    content = models.TextField(blank=True, null=True)

    # Stores uploaded file (image/audio/etc.)
    file_url = models.TextField(blank=True, null=True)

    # Raw metadata (duration, format, file_size, AI-debug-info, etc.)
    metadata = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "chat_messages"
        ordering = ["created_at"]

    def __str__(self):
        if self.message_type == "text":
            return f"[{self.role}] {self.content[:40]}"
        return f"[{self.role}] ({self.message_type} message)"
