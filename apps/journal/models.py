# apps/journal/models/JournalEntry.py

from django.db import models
from apps.authentication.models import User
from apps.events.models.BaseModel import BaseModel


class JournalEntry(BaseModel):

    MOOD_CHOICES = [
        ("peaceful", "Peaceful"),
        ("joyful", "Joyful"),
        ("enlightened", "Enlightened"),
        ("reflective", "Reflective"),
        ("emotional", "Emotional"),
    ]

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="journal_entries"
    )

    title = models.CharField(max_length=255)

    # User written content OR AI prompt starter question
    notes = models.TextField()

    ai_prompt = models.TextField(
        null=True,
        blank=True
    )

    # Full AI generated reflection
    ai_reflection = models.TextField(
        null=True,
        blank=True
    )

    mood = models.CharField(
        max_length=50,
        choices=MOOD_CHOICES,
        null=True,
        blank=True
    )

    photo = models.ImageField(
        upload_to="journal_photos/",
        null=True,
        blank=True
    )



    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user} - {self.title}"
    


class SpiritualPrinciple(BaseModel):

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="spiritual_principles"
    )

    content = models.TextField()

    source = models.CharField(
        max_length=50,
        default="ai",  # ai / user
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user} - Principle"