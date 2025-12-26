# apps/aiChat/serializers.py

import os
import base64
import requests
from utils.audio import convert_audio_to_mp3

from django.core.files.storage import default_storage
from django.utils import timezone
from rest_framework import serializers

from apps.aiChat.models import ChatSession, ChatMessage

# n8n webhook URL
N8N_WEBHOOK_URL = "https://permeant-elbert-sulkier.ngrok-free.dev/webhook-test/chat"
# alternatives (commented)
# N8N_WEBHOOK_URL = "https://workflows.softwarecompanyindia.com/webhook/chat"




class ChatRequestSerializer(serializers.Serializer):
    """
    Handles sending a chat message (text / image / audio / file) to:
    - Save in DB
    - Call n8n webhook (with Base64 for files)
    - Store assistant response
    """

    message = serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=True,
    )

    session_id = serializers.UUIDField(required=False, allow_null=True)

    file = serializers.FileField(
        required=False,
        allow_null=True,
    )

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

        # Decide message_type
        message_type = "text"
        if upload_file:
            content_type = getattr(upload_file, "content_type", "") or ""
            if content_type.startswith("image/"):
                message_type = "image"
            elif content_type.startswith("audio/"):
                message_type = "audio"
            else:
                message_type = "file"

        attrs["message"] = message or ""
        attrs["user"] = user
        attrs["session"] = session
        attrs["message_type"] = message_type

        return attrs

    def create(self, validated_data):
        user = validated_data["user"]
        session = validated_data["session"]
        message_text = validated_data["message"]
        message_type = validated_data["message_type"]
        upload_file = validated_data.get("file")

        file_url = None
        file_storage_name = None
        metadata = {}

        # Save uploaded file
        if upload_file:
            folder = f"chat/{user.user_id}"
            file_storage_name = default_storage.save(
                os.path.join(folder, upload_file.name),
                upload_file,
            )
            file_url = default_storage.url(file_storage_name)

            metadata = {
                "original_name": upload_file.name,
                "content_type": getattr(upload_file, "content_type", None),
                "size": upload_file.size,
            }

        # Save USER message
        user_msg = ChatMessage.objects.create(
            session=session,
            user=user,
            role="user",
            message_type=message_type,
            content=message_text if message_type == "text" else None,
            file_url=file_url,
            metadata=metadata,
        )

        # Call n8n webhook
        try:
            payload = {
                "session_id": str(session.session_id),
                "user_id": str(user.user_id),
                "message_type": message_type,
                "message": message_text,
                "file_url": file_url,
                "metadata": metadata,
            }

            # Handle Base64 for files
            if upload_file and file_storage_name:
                file_path = default_storage.path(file_storage_name)

                # Convert audio to MP3
                if message_type == "audio":
                    try:
                        mp3_path = convert_audio_to_mp3(file_path)
                        file_path = mp3_path
                        metadata["content_type"] = "audio/mpeg"
                        metadata["original_name"] = os.path.basename(mp3_path)
                    except Exception as e:
                        metadata["audio_conversion_error"] = str(e)

                with open(file_path, "rb") as f:
                    file_bytes = f.read()

                payload["file_base64"] = base64.b64encode(file_bytes).decode("utf-8")
                payload["file_name"] = metadata.get("original_name")
                payload["file_mime"] = metadata.get("content_type")

            n8n_response = requests.post(
                N8N_WEBHOOK_URL,
                json=payload,
                timeout=30,
            )
            n8n_response.raise_for_status()

            try:
                n8n_data = n8n_response.json()
            except ValueError:
                n8n_data = {"raw": n8n_response.text}

            assistant_text = (
                n8n_data.get("reply")
                or n8n_data.get("message")
                or str(n8n_data)
            )

        except Exception as e:
            assistant_text = "Sorry, I am unable to respond right now."
            n8n_data = {"error": str(e)}

        # Save ASSISTANT message
        assistant_msg = ChatMessage.objects.create(
            session=session,
            role="assistant",
            message_type="text",
            content=assistant_text,
            metadata={"n8n_raw": n8n_data},
        )

        # Update session timestamp
        session.last_message_at = timezone.now()
        session.save(update_fields=["last_message_at"])

        # Response payload
        return {
            "session_id": str(session.session_id),
            "messages": [
                {
                    "message_id": user_msg.message_id,
                    "role": user_msg.role,
                    "content": user_msg.content,
                    "file_url": user_msg.file_url,
                    "metadata": user_msg.metadata,
                    "created_at": user_msg.created_at,
                    "session_id": str(session.session_id),
                },
                {
                    "message_id": assistant_msg.message_id,
                    "role": assistant_msg.role,
                    "message_type": assistant_msg.message_type,
                    "content": assistant_msg.content,
                    "file_url": None,
                    "created_at": assistant_msg.created_at,
                    "session_id": str(session.session_id),
                },
            ],
        }

# class ChatRequestSerializer(serializers.Serializer):
#     """
#     Handles sending a chat message (text / image / audio / file) to:
#     - Save in DB
#     - Call n8n webhook (with Base64 for files)
#     - Store assistant response
#     """

#     # text content (optional; can be empty for pure file messages)
#     message = serializers.CharField(
#         required=False,
#         allow_blank=True,
#         allow_null=True,
#     )

#     # optional – if not sent, we reuse latest session for the user
#     session_id = serializers.UUIDField(required=False, allow_null=True)

#     # file for image / audio / other
#     file = serializers.FileField(
#         required=False,
#         allow_null=True,
#     )

#     def validate(self, attrs):
#         request = self.context["request"]
#         user = request.user
#         session_id = attrs.get("session_id")
#         message = attrs.get("message")
#         upload_file = attrs.get("file")

#         # 0️⃣ Ensure at least text or file is present
#         if (not message or str(message).strip() == "") and not upload_file:
#             raise serializers.ValidationError(
#                 {"message": "Either 'message' text or 'file' is required."}
#             )

#         # 1️⃣ Find or create session
#         if session_id:
#             try:
#                 session = ChatSession.objects.get(
#                     session_id=session_id,
#                     user=user,
#                     del_flag=0,
#                 )
#             except ChatSession.DoesNotExist:
#                 raise serializers.ValidationError(
#                     {"session_id": "Chat session not found"}
#                 )
#         else:
#             # Reuse latest session for this user & mode
#             session = (
#                 ChatSession.objects
#                 .filter(user=user, mode="guru_ai", del_flag=0)
#                 .order_by("-created_at")
#                 .first()
#             )

#             # If no existing session → create a new one
#             if session is None:
#                 session = ChatSession.objects.create(
#                     user=user,
#                     title="Ask Guru AI",
#                     mode="guru_ai",
#                 )

#         # 2️⃣ Decide message_type based on file (if any)
#         message_type = "text"
#         if upload_file:
#             content_type = getattr(upload_file, "content_type", "") or ""
#             if content_type.startswith("image/"):
#                 message_type = "image"
#             elif content_type.startswith("audio/"):
#                 message_type = "audio"
#             else:
#                 message_type = "file"

#         # Normalize message (avoid None)
#         attrs["message"] = message or ""
#         attrs["user"] = user
#         attrs["session"] = session
#         attrs["message_type"] = message_type

#         return attrs

#     def create(self, validated_data):
#         user = validated_data["user"]
#         session = validated_data["session"]
#         message_text = validated_data["message"]
#         message_type = validated_data["message_type"]
#         upload_file = validated_data.get("file")

#         file_url = None
#         file_storage_name = None
#         metadata = {}

#         # 1️⃣ Handle file upload if present
#         if upload_file:
#             folder = f"chat/{user.user_id}"
#             file_storage_name = default_storage.save(
#                 os.path.join(folder, upload_file.name),
#                 upload_file,
#             )
#             file_url = default_storage.url(file_storage_name)
#             metadata.update(
#                 {
#                     "original_name": upload_file.name,
#                     "content_type": getattr(upload_file, "content_type", None),
#                     "size": upload_file.size,
#                 }
#             )

#         user_msg = ChatMessage.objects.create(
#             session=session,
#             user=user,
#             role="user",
#             message_type=message_type,
#             content=message_text if message_type == "text" else None,
#             file_url=file_url,
#             metadata=metadata,
#         )

#         # 3️⃣ Call n8n webhook for ALL message types (with base64 if file)
#         assistant_msg = None
#         try:
#             payload = {
#                 "session_id": str(session.session_id),
#                 "user_id": str(user.user_id),
#                 "message_type": message_type,
#                 "message": message_text,
#                 "file_url": file_url,   # still useful for frontend / logs
#                 "metadata": metadata,
#             }

#             # If file exists → send Base64 in payload
            
#             # if upload_file and file_storage_name:
#             #     try:
#             #         # Get absolute storage path
#             #         file_path = default_storage.path(file_storage_name)
#             #         with open(file_path, "rb") as f:
#             #             file_bytes = f.read()
#             #         file_b64 = base64.b64encode(file_bytes).decode("utf-8")

#             #         payload["file_base64"] = file_b64
#             #         payload["file_name"] = upload_file.name
#             #         payload["file_mime"] = metadata.get("content_type")
#             #     except Exception as read_err:
#             #         # If reading fails, still continue with URL & metadata
#             #         payload["file_read_error"] = str(read_err)

#             # POST to webhook
#             n8n_response = requests.post(
#                 N8N_WEBHOOK_URL,
#                 json=payload,
#                 timeout=30,
#             )
#             n8n_response.raise_for_status()

#             # Try to parse JSON; if not JSON, fallback to raw text
#             try:
#                 n8n_data = n8n_response.json()
#             except ValueError:
#                 n8n_data = {"raw": n8n_response.text}

#             assistant_text = (
#                 n8n_data.get("reply")
#                 or n8n_data.get("message")
#                 or str(n8n_data)
#             )

#         except Exception as e:
#             assistant_text = "Sorry, I am unable to respond right now."
#             n8n_data = {"error": str(e)}

#         # 4️⃣ Save ASSISTANT message (text reply) in DB
#         assistant_msg = ChatMessage.objects.create(
#             session=session,
#             role="assistant",
#             message_type="text",
#             content=assistant_text,
#             metadata={"n8n_raw": n8n_data},
#         )

#         # 5️⃣ Update session timestamps
#         session.last_message_at = timezone.now()
#         session.save(update_fields=["last_message_at"])

#         # 6️⃣ Build response payload for client
#         messages_payload = [
#             {
#                 "message_id": user_msg.message_id,
#                 "role": user_msg.role,
#                 # "message_type": user_msg.message_type,
#                 "content": user_msg.content,
#                 "file_url": user_msg.file_url,
#                 "metadata": user_msg.metadata,
#                 "created_at": user_msg.created_at,
#                 "session_id": str(session.session_id),
#             },
#             {
#                 "message_id": assistant_msg.message_id,
#                 "role": assistant_msg.role,
#                 "message_type": assistant_msg.message_type,
#                 "content": assistant_msg.content,
#                 "file_url": getattr(assistant_msg, "file_url", None),
#                 # "metadata": assistant_msg.metadata,
#                 "session_id": str(session.session_id),
#                 "created_at": assistant_msg.created_at,
#             },
#         ]

#         return {
#             "session_id": str(session.session_id),
#             "messages": messages_payload,
#         }


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
        limit = min(attrs.get("limit", 10), 50)
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
                {
                    "message_id": msg.message_id,
                    "role": msg.role,
                    "message_type": msg.message_type,
                    "content": msg.content,
                    "file_url": msg.file_url,
                    "metadata": msg.metadata,
                    "created_at": msg.created_at,
                }
                for msg in reversed(messages)  # oldest ➜ newest for UI
            ],
            "has_more": has_more,
            "next_cursor": next_cursor,
        }
