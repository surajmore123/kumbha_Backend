"""
Conversation context for follow-up questions.

Only the current session is read (sessions are already owner-checked by
the serializer), only the last few messages, and only up to a character
budget, so the whole conversation is never sent to the model.
"""

from apps.aiChat import ai_config
from apps.aiChat.models import ChatMessage

INTERNAL_KEY = "_internal"
_PER_MESSAGE_CHARS = 600


def public_metadata(metadata: dict | None) -> dict:
    """Metadata as returned by the API: internal storage keys removed."""
    if not isinstance(metadata, dict):
        return {}
    return {k: v for k, v in metadata.items() if k != INTERNAL_KEY}


def _message_text(message: ChatMessage) -> str:
    metadata = message.metadata if isinstance(message.metadata, dict) else {}
    text = (message.content or "").strip()
    if message.role == "user" and message.message_type != "text":
        transcript = (metadata.get("transcript") or {}).get("text")
        label = {
            "image": "[sent an image]",
            "audio": "[sent a voice message]",
            "file": "[sent a document"
            + (f": {metadata.get('original_name')}" if metadata.get("original_name") else "")
            + "]",
        }.get(message.message_type, "[sent a file]")
        parts = [label]
        if transcript:
            parts.append(f"Transcript: {transcript}")
        if text:
            parts.append(text)
        text = " ".join(parts)
    if len(text) > _PER_MESSAGE_CHARS:
        text = text[:_PER_MESSAGE_CHARS] + "…"
    return text


def build_context(session, user, exclude_message_id=None) -> dict:
    """Recent turns plus references the next question may point back to."""
    limit = ai_config.history_max_messages()
    context = {
        "turns": [],
        "last_route": None,
        "last_intents": [],
        "last_temple_ids": [],
        "last_event_ids": [],
        "document": None,
        "image": None,
    }
    if limit <= 0:
        return context

    queryset = ChatMessage.objects.filter(session=session, del_flag=0)
    if exclude_message_id is not None:
        queryset = queryset.exclude(message_id=exclude_message_id)
    recent = list(queryset.order_by("-message_id")[:limit])

    budget = ai_config.history_max_chars()
    turns = []
    for position, message in enumerate(recent):  # newest first
        metadata = message.metadata if isinstance(message.metadata, dict) else {}
        internal = metadata.get(INTERNAL_KEY) or {}

        if message.role == "assistant" and context["last_route"] is None:
            context["last_route"] = metadata.get("route")
            context["last_intents"] = list(metadata.get("intents") or [])
            context["last_temple_ids"] = [
                t.get("id") for t in metadata.get("temples") or [] if isinstance(t, dict)
            ]
            context["last_event_ids"] = [
                e.get("id") for e in metadata.get("events") or [] if isinstance(e, dict)
            ]

        if message.role == "user" and message.user_id == getattr(user, "pk", None):
            if context["document"] is None and internal.get("extract_key"):
                context["document"] = {
                    "extract_key": internal["extract_key"],
                    "name": metadata.get("original_name") or "document",
                }
            # Only a recent image can be meant by "this photo".
            if (
                context["image"] is None
                and position < 4
                and message.message_type == "image"
                and internal.get("storage_key")
            ):
                context["image"] = {
                    "storage_key": internal["storage_key"],
                    "mime_type": metadata.get("content_type") or "image/jpeg",
                }

        text = _message_text(message)
        if text and budget > 0:
            text = text[:budget]
            budget -= len(text)
            turns.append({"role": message.role, "text": text})

    context["turns"] = list(reversed(turns))
    return context
