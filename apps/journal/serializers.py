from rest_framework import serializers
from apps.journal.models import JournalEntry


class JournalEntrySerializer(serializers.ModelSerializer):

    ai_prompt = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    ai_reflection = serializers.CharField(required=False, allow_null=True, allow_blank=True)

    class Meta:
        model = JournalEntry
        fields = [
            "id",
            "title",
            "notes",
            "ai_prompt",
            "ai_reflection",
            "mood",
            "photo",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]

    def create(self, validated_data):
        user = self.context["request"].user
        return JournalEntry.objects.create(user=user, **validated_data)
    

