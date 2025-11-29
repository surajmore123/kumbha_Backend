# apps/aiChat/serializers.py

import requests
from django.utils import timezone
from rest_framework import serializers
from apps.aiChat.models import ChatSession, ChatMessage

N8N_WEBHOOK_URL = "https://permeant-elbert-sulkier.ngrok-free.dev/webhook/chat"


class ChatRequestSerializer(serializers.Serializer):
    message = serializers.CharField()
    session_id = serializers.UUIDField(required=False, allow_null=True)

    def validate(self, attrs):
        user = self.context["request"].user
        session_id = attrs.get("session_id")

        # DEBUG (optional, to see what's coming from client)
        # print("DEBUG user:", user.user_id, "session_id from request:", session_id)

        # 1️⃣ If client sends a session_id → use that specific session
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
            # 2️⃣ No session_id → reuse the latest session for this user
            session = (
                ChatSession.objects
                .filter(user=user, mode="guru_ai", del_flag=0)
                .order_by("-created_at")
                .first()
            )

            # 3️⃣ If user has no previous sessions → create a new one
            if session is None:
                session = ChatSession.objects.create(
                    user=user,
                    title="Ask Guru AI",
                    mode="guru_ai",
                )

        attrs["session"] = session
        attrs["user"] = user
        return attrs

    def create(self, validated_data):
        user = validated_data["user"]
        session = validated_data["session"]
        message_text = validated_data["message"]

        # 1️⃣ Save USER message
        user_msg = ChatMessage.objects.create(
            session=session,
            user=user,
            role="user",
            content=message_text,
            message_type="text",
        )

        # 2️⃣ Call N8N webhook
        try:
            n8n_response = requests.post(
                N8N_WEBHOOK_URL,
                json={"message": message_text},
                timeout=30,
            )
            n8n_response.raise_for_status()
            n8n_data = n8n_response.json()

            assistant_text = (
                n8n_data.get("reply")
                or n8n_data.get("message")
                or str(n8n_data)
            )

        except Exception as e:
            assistant_text = "Sorry, I am unable to respond right now."
            n8n_data = {"error": str(e)}

        # 3️⃣ Save ASSISTANT message
        assistant_msg = ChatMessage.objects.create(
            session=session,
            role="assistant",
            content=assistant_text,
            metadata={"n8n_raw": n8n_data},
            message_type="text",
        )

        # 4️⃣ Update session timestamps
        session.last_message_at = timezone.now()
        session.save(update_fields=["last_message_at"])

        # 5️⃣ Return final response
        return {
            "session_id": str(session.session_id),
            "messages": [
                {
                    "role": "user",
                    "content": user_msg.content,
                    "created_at": user_msg.created_at,
                },
                {
                    "role": "assistant",
                    "content": assistant_msg.content,
                    "created_at": assistant_msg.created_at,
                },
            ],
        }



class ChatHistorySerializer(serializers.Serializer):
    # now optional – backend can decide
    session_id = serializers.UUIDField(required=False)
    cursor = serializers.IntegerField(required=False)
    limit = serializers.IntegerField(required=False, default=20)

    def validate(self, attrs):
        request = self.context["request"]
        user = request.user

        # pagination guard
        limit = attrs.get("limit", 20)
        limit = min(limit, 50)
        attrs["limit"] = limit

        # optional cursor (we don't need it in validate)
        cursor = attrs.get("cursor")

        # 🔹 session_id may or may not be provided
        session_id = attrs.get("session_id")

        if session_id:
            # Use the specific session passed from client
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
            # No session_id → reuse latest session OR create a fresh empty one
            session = (
                ChatSession.objects
                .filter(user=user, mode="guru_ai", del_flag=0)
                .order_by("-created_at")
                .first()
            )

            if session is None:
                # user has no previous sessions → create a new one so
                # frontend still gets a valid session_id back
                session = ChatSession.objects.create(
                    user=user,
                    title="Ask Guru AI",
                    mode="guru_ai",
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
            .order_by("-message_id")  # newest → oldest
        )

        if cursor:
            queryset = queryset.filter(message_id__lt=cursor)

        messages = list(queryset[: limit + 1 ])  # fetch one extra to detect has_more
        has_more = len(messages) > limit
        messages = messages[:limit]

        next_cursor = messages[-1].message_id if messages else None

        return {
            "session_id": str(session.session_id),
            "messages": [
                {
                    "message_id": msg.message_id,
                    "role": msg.role,
                    "content": msg.content,
                    "created_at": msg.created_at,
                }
                for msg in reversed(messages)  # oldest → newest for UI
            ],
            "has_more": has_more,
            "next_cursor": next_cursor,
        }

