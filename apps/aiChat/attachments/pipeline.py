"""Turn an upload into a validated, model-ready attachment."""

import os
from dataclasses import dataclass, field

from apps.aiChat.attachments import detection
from apps.aiChat.attachments.audio import prepare_audio
from apps.aiChat.attachments.documents import ExtractedDocument, extract_document
from apps.aiChat.attachments.errors import AttachmentError
from apps.aiChat.attachments.images import prepare_image

MESSAGE_TYPES = {
    detection.IMAGE: "image",
    detection.AUDIO: "audio",
    detection.DOCUMENT: "file",
}


@dataclass
class PreparedUpload:
    kind: str                 # "image" | "audio" | "document"
    mime_type: str            # type of `data` (after any conversion)
    extension: str
    data: bytes               # what is stored and sent to the model
    original_name: str
    original_size: int
    details: dict = field(default_factory=dict)
    document: ExtractedDocument | None = None

    @property
    def message_type(self) -> str:
        return MESSAGE_TYPES[self.kind]


def display_name(filename: str | None) -> str:
    """Client filename for display only (never used as a storage path)."""
    name = os.path.basename((filename or "").replace("\\", "/")).strip()
    return name[:120] or "upload"


def prepare_upload(
    data: bytes,
    filename: str | None,
    declared_type: str | None,
) -> PreparedUpload:
    """Raises `AttachmentError` with a user-facing message code."""
    detected = detection.detect_file(data, filename, declared_type)
    name = display_name(filename)

    if detected.kind == detection.IMAGE:
        image = prepare_image(data, detected.mime_type)
        return PreparedUpload(
            kind="image",
            mime_type=image.mime_type,
            extension=image.extension,
            data=image.data,
            original_name=name,
            original_size=len(data),
            details={"width": image.width, "height": image.height},
        )

    if detected.kind == detection.AUDIO:
        audio = prepare_audio(data, detected.mime_type)
        details = {"converted": audio.converted}
        if audio.duration_seconds is not None:
            details["duration_seconds"] = round(audio.duration_seconds, 1)
        return PreparedUpload(
            kind="audio",
            mime_type=audio.mime_type,
            extension=audio.extension,
            data=audio.data,
            original_name=name,
            original_size=len(data),
            details=details,
        )

    document = extract_document(data, detected.mime_type, name)
    return PreparedUpload(
        kind="document",
        mime_type=detected.mime_type,
        extension=detected.extension,
        data=data,
        original_name=name,
        original_size=len(data),
        details={
            key: value
            for key, value in {
                "page_count": document.page_count,
                "pages_read": document.pages_read,
                "truncated": document.truncated or None,
                "scanned": document.scanned or None,
            }.items()
            if value is not None
        },
        document=document,
    )


__all__ = ["AttachmentError", "PreparedUpload", "prepare_upload", "display_name"]
