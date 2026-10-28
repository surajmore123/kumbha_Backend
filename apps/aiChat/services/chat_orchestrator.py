"""
One chat turn: persist the user's message, run the graph, persist the reply.

    request → validate upload → store user message → conversation context
            → LangGraph (understand → route → gather → compose)
            → document extract / transcript / optional voice → store reply

The serializer handles request validation and the response shape; this
module holds the processing so it stays out of the serializer.
"""

import logging
import time

from django.db import transaction
from django.utils import timezone

from apps.aiChat import ai_config, messages
from apps.aiChat.attachments import storage
from apps.aiChat.attachments.errors import AttachmentError
from apps.aiChat.attachments.pipeline import (
    MESSAGE_TYPES,
    PreparedUpload,
    display_name,
    prepare_upload,
)
from apps.aiChat.graph import chat_graph
from apps.aiChat.models import ChatMessage, ChatSession
from apps.aiChat.services.history_service import INTERNAL_KEY, build_context
from apps.aiChat.services.language_service import fixed_message, localize
from apps.aiChat.services.n8n_service import send_to_n8n
from apps.aiChat.services.voice_service import VoiceServiceError, synthesize_speech

logger = logging.getLogger(__name__)


def _error_text(error: AttachmentError, language: str) -> str:
    code = "no_speech" if error.code == "silent_audio" else error.code
    try:
        text = messages.message(code, language, **error.params)
    except KeyError:
        text = messages.message("unsupported_file", language)
    return localize(text, language)


def _user_metadata(upload: PreparedUpload, storage_key: str) -> dict:
    return {
        # Existing keys: the app picks image/audio bubbles from content_type.
        "original_name": upload.original_name,
        "content_type": upload.mime_type,
        "size": upload.original_size,
        "attachment": {"kind": upload.kind, **upload.details},
        INTERNAL_KEY: {"storage_key": storage_key},
    }


def _legacy_n8n_turn(user, session, text, raw, filename, declared_type):
    """AI_MEDIA_PIPELINE=n8n: previous behaviour for uploads."""
    content_type = (declared_type or "").lower()
    message_type = (
        "image" if content_type.startswith("image/")
        else "audio" if content_type.startswith("audio/")
        else "file"
    )
    data = raw
    metadata = {
        "original_name": display_name(filename),
        "content_type": declared_type,
        "size": len(raw),
    }
    if message_type == "audio":
        try:
            upload = prepare_upload(raw, filename, declared_type)
            if upload.kind == "audio" and upload.mime_type == "audio/mp3":
                data = upload.data
                metadata["content_type"] = "audio/mpeg"
        except AttachmentError:
            metadata["audio_conversion_error"] = "Audio conversion failed"

    extension = "." + (filename or "").rsplit(".", 1)[-1].lower()[:5] if "." in (filename or "") else ""
    key = storage.save_bytes(user.user_id, data, extension)
    file_url = storage.url_for(key)
    user_msg = ChatMessage.objects.create(
        session=session, user=user, role="user", message_type=message_type,
        content=text or None, file_url=file_url,
        metadata={**metadata, INTERNAL_KEY: {"storage_key": key}},
    )
    reply, reply_meta = send_to_n8n(
        session_id=str(session.session_id),
        user_id=str(user.user_id),
        message_type=message_type,
        message=text,
        file_url=file_url,
        metadata=metadata,
        data=data,
    )
    return user_msg, reply, reply_meta


def handle_turn(
    *,
    user,
    session: ChatSession,
    text: str,
    upload_file=None,
    language: str = "",
    location: dict | None = None,
    voice_reply: bool = False,
) -> tuple[ChatMessage, ChatMessage]:
    started = time.monotonic()
    text = (text or "").strip()
    # The app's UI language is only a fallback: the question's own
    # language (or an explicit "answer in Marathi") decides the reply.
    app_language = messages.normalize_language(language)
    language_info = messages.analyze_language(text, app_language)
    reply_language = language_info.code

    raw = filename = declared_type = None
    if upload_file is not None:
        filename = getattr(upload_file, "name", None)
        declared_type = getattr(upload_file, "content_type", None)
        raw = upload_file.read()

    # ---- legacy n8n fallback -------------------------------------------------
    if raw is not None and ai_config.media_pipeline() == "n8n":
        user_msg, reply, reply_meta = _legacy_n8n_turn(
            user, session, text, raw, filename, declared_type,
        )
        return user_msg, _save_reply(session, reply, reply_meta)

    # ---- prepare the upload -----------------------------------------------------
    upload: PreparedUpload | None = None
    rejection: AttachmentError | None = None
    if raw is not None:
        try:
            upload = prepare_upload(raw, filename, declared_type)
        except AttachmentError as error:
            rejection = error

    if upload is not None:
        storage_key = storage.save_bytes(user.user_id, upload.data, upload.extension)
        user_msg = ChatMessage.objects.create(
            session=session, user=user, role="user",
            message_type=upload.message_type,
            content=text or None,
            file_url=storage.url_for(storage_key),
            metadata=_user_metadata(upload, storage_key),
        )
    else:
        metadata = {}
        if rejection is not None:
            # Rejected files are not stored.
            metadata = {
                "original_name": display_name(filename),
                "size": len(raw or b""),
                "attachment": {"rejected": True, "reason": rejection.code},
            }
        user_msg = ChatMessage.objects.create(
            session=session, user=user, role="user",
            message_type="file" if rejection is not None else "text",
            content=text, metadata=metadata,
        )

    if rejection is not None:
        logger.info("Upload rejected (%s) in session %s.", rejection.code, session.session_id)
        reply_meta = {
            "provider": "langgraph", "route": "attachment", "status": "rejected",
            "error": rejection.code, "language": reply_language,
            "sources": [], "temples": [],
        }
        return user_msg, _save_reply(session, _error_text(rejection, reply_language), reply_meta)

    # ---- run the graph -------------------------------------------------------------
    history = build_context(session, user, exclude_message_id=user_msg.message_id)
    state = {
        "question": text,
        "user_message": text,
        "answer": "",
        "sources": [],
        "route": "",
        "temples": [],
        "user_id": str(user.user_id),
        "language": reply_language,
        "language_info": {
            "code": language_info.code,
            "romanized": language_info.romanized,
            "explicit": language_info.explicit,
            "source": language_info.source,
        },
        "app_language": app_language,
        "location": location,
        "history": history,
        "deadline": started + ai_config.request_budget_seconds(),
        "attachment": (
            {
                "kind": upload.kind,
                "mime_type": upload.mime_type,
                "data": upload.data,
                "name": upload.original_name,
                "document": upload.document,
            }
            if upload is not None else None
        ),
    }

    try:
        result = chat_graph.invoke(state)
    except Exception:  # noqa: BLE001 - the user still gets a reply
        logger.exception("LangGraph failed for chat session %s", session.session_id)
        reply_meta = {
            "provider": "langgraph", "status": "error",
            "error": "Chat processing failed", "language": reply_language,
            "sources": [], "temples": [],
        }
        failed = {
            "image": "image_failed", "audio": "audio_failed", "document": "document_failed",
        }.get(upload.kind if upload else "", "unavailable")
        return user_msg, _save_reply(session, fixed_message(failed, reply_language), reply_meta)

    language = result.get("language") or reply_language
    _update_user_message(user, user_msg, upload, result)

    reply_meta = {
        "provider": "langgraph",
        "route": result.get("route"),
        "intents": result.get("intents") or [],
        "status": result.get("status") or "ok",
        "language": language,
        "sources": result.get("sources", []),
        "citations": result.get("citations", []),
        "temples": result.get("temples", []),
        "events": result.get("events", []),
        # Which list the cards show, e.g. "nearby" temples or "recent" changes.
        "temple_mode": result.get("temple_mode"),
        "event_mode": result.get("event_mode"),
    }
    if result.get("crowd"):
        reply_meta["crowd"] = result["crowd"]
    if result.get("transcript"):
        reply_meta["transcript"] = result["transcript"]
    if result.get("errors"):
        reply_meta["warnings"] = result["errors"]

    answer = result.get("answer") or fixed_message("unavailable", language)
    if voice_reply:
        reply_meta["voice"] = _voice_reply(user, answer, started)
    return user_msg, _save_reply(session, answer, reply_meta)


def _update_user_message(user, user_msg: ChatMessage, upload, result: dict) -> None:
    """Keep what later turns need: the transcript and the document text."""
    if upload is None:
        return
    metadata = dict(user_msg.metadata or {})
    internal = dict(metadata.get(INTERNAL_KEY) or {})
    changed = False

    if result.get("transcript"):
        metadata["transcript"] = result["transcript"]
        changed = True

    document = upload.document
    if document is not None and document.sections:
        internal["extract_key"] = storage.save_json(
            user.user_id, document.to_dict(), "extracts",
        )
        attachment = dict(metadata.get("attachment") or {})
        if document.ocr_used:
            attachment["ocr_used"] = True
        attachment["characters"] = document.char_count
        metadata["attachment"] = attachment
        changed = True

    if changed:
        metadata[INTERNAL_KEY] = internal
        user_msg.metadata = metadata
        user_msg.save(update_fields=["metadata"])


def _voice_reply(user, answer: str, started: float) -> dict:
    if not ai_config.voice_reply_enabled():
        return {"status": "disabled"}
    remaining = started + ai_config.request_budget_seconds() - time.monotonic()
    try:
        wav = synthesize_speech(answer, timeout=remaining)
    except VoiceServiceError:
        return {"status": "failed"}
    key = storage.save_bytes(user.user_id, wav, ".wav", "voice")
    return {"status": "ok", "url": storage.url_for(key), "mime_type": "audio/wav"}


def _save_reply(session: ChatSession, text: str, metadata: dict) -> ChatMessage:
    with transaction.atomic():
        reply = ChatMessage.objects.create(
            session=session,
            role="assistant",
            message_type="text",
            content=text,
            metadata=metadata,
        )
        ChatSession.objects.filter(pk=session.pk).update(last_message_at=timezone.now())
    return reply


__all__ = ["handle_turn", "MESSAGE_TYPES"]
