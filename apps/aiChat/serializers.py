# apps/aiChat/serializers.py

from rest_framework import serializers

from apps.aiChat import ai_config
from apps.aiChat.models import ChatSession, ChatMessage
from apps.aiChat.services.chat_orchestrator import handle_turn
from apps.aiChat.services.geo import valid_coordinates
from apps.aiChat.services.history_service import public_metadata

# Anything larger than the largest per-type limit is refused before it is
# read; per-type limits are applied when the file is processed.
MAX_MESSAGE_CHARS = 4000


def _max_upload_bytes() -> int:
    return max(
        ai_config.max_image_bytes(),
        ai_config.max_audio_bytes(),
        ai_config.max_document_bytes(),
    )


def _message_dict(message: ChatMessage, session_id: str | None = None) -> dict:
    data = {
        "message_id": message.message_id,
        "role": message.role,
        "message_type": message.message_type,
        "content": message.content,
        "file_url": message.file_url,
        "metadata": public_metadata(message.metadata),
        "created_at": message.created_at,
    }
    if session_id is not None:
        data["session_id"] = session_id
    return data


class ChatRequestSerializer(serializers.Serializer):
    """
    Handles sending a chat message (text / image / audio / document):
    validates the request and session, hands the turn to
    `chat_orchestrator.handle_turn` and returns the stored messages.
    """

    message = serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=True,
        max_length=MAX_MESSAGE_CHARS,
    )

    session_id = serializers.UUIDField(required=False, allow_null=True)

    file = serializers.FileField(
        required=False,
        allow_null=True,
    )

    # Optional, additive fields (older clients don't send them).
    language = serializers.ChoiceField(
        choices=["en", "hi", "mr"], required=False, allow_blank=True,
    )
    latitude = serializers.FloatField(required=False, allow_null=True)
    longitude = serializers.FloatField(required=False, allow_null=True)
    voice_reply = serializers.BooleanField(required=False, default=False)

    def validate(self, attrs):
        request = self.context["request"]
        user = request.user
        session_id = attrs.get("session_id")
        message = attrs.get("message")
        upload_file = attrs.get("file")

        # Ensure at least text or file is present
        if (not message or str(message).strip() == "") and not upload_file:
            raise serializers.ValidationError(
                {"message": "Either 'message' text or 'file' is required."}
            )

        if upload_file and upload_file.size > _max_upload_bytes():
            raise serializers.ValidationError(
                {"file": f"File is too large (max {_max_upload_bytes() // (1024 * 1024)} MB)."}
            )

        latitude, longitude = attrs.get("latitude"), attrs.get("longitude")
        if latitude is not None or longitude is not None:
            if not valid_coordinates(latitude, longitude):
                raise serializers.ValidationError(
                    {"latitude": "A valid latitude and longitude are both required."}
                )
            attrs["location"] = {"latitude": latitude, "longitude": longitude}

        # Find or create session
        if session_id:
            try:
                session = ChatSession.objects.get(
                    session_id=session_id,
                    user=user,
                    del_flag=0,
                )
            except ChatSession.DoesNotExist:
                raise serializers.ValidationError(
                    {"session_id": "Chat session not found"}
                )
        else:
            session = (
                ChatSession.objects
                .filter(user=user, mode="guru_ai", del_flag=0)
                .order_by("-created_at")
                .first()
            )

            if session is None:
                session = ChatSession.objects.create(
                    user=user,
                    title="Ask Guru AI",
                    mode="guru_ai",
                )

        attrs["message"] = message or ""
        attrs["user"] = user
        attrs["session"] = session

        return attrs

    def create(self, validated_data):
        session = validated_data["session"]
        session_id = str(session.session_id)

        user_msg, assistant_msg = handle_turn(
            user=validated_data["user"],
            session=session,
            text=validated_data["message"],
            upload_file=validated_data.get("file"),
            language=validated_data.get("language") or "",
            location=validated_data.get("location"),
            voice_reply=validated_data.get("voice_reply", False),
        )

        # Return the existing API structure.
        return {
            "session_id": session_id,
            "messages": [
                _message_dict(user_msg, session_id),
                _message_dict(assistant_msg, session_id),
            ],
        }


class ChatHistorySerializer(serializers.Serializer):
    """
    Returns paginated chat history for a given session.
    Supports cursor-based pagination using message_id.
    """

    session_id = serializers.UUIDField()
    cursor = serializers.IntegerField(required=False)  # message_id
    limit = serializers.IntegerField(required=False, default=10)

    def validate(self, attrs):
        request = self.context["request"]
        user = request.user

        # sanitize limit
        limit = max(1, min(attrs.get("limit", 10), 50))
        attrs["limit"] = limit

        # validate session
        try:
            session = ChatSession.objects.get(
                session_id=attrs["session_id"],
                user=user,
                del_flag=0,
            )
        except ChatSession.DoesNotExist:
            raise serializers.ValidationError(
                {"session_id": "Chat session not found"}
            )

        attrs["session"] = session
        return attrs

    def create(self, validated_data):
        session = validated_data["session"]
        cursor = validated_data.get("cursor")
        limit = validated_data["limit"]

        queryset = (
            ChatMessage.objects
            .filter(session=session)
            .order_by("-message_id")  # newest ➜ oldest
        )

        # cursor pagination: load messages with id < cursor
        if cursor:
            queryset = queryset.filter(message_id__lt=cursor)

        # fetch limit+1 to know if there are more
        messages = list(queryset[: limit + 1])
        has_more = len(messages) > limit
        messages = messages[:limit]

        next_cursor = messages[-1].message_id if messages else None

        return {
            "session_id": str(session.session_id),
            "messages": [
                _message_dict(msg)
                for msg in reversed(messages)  # oldest ➜ newest for UI
            ],
            "has_more": has_more,
            "next_cursor": next_cursor,
        }
