"""
Work out what an uploaded file really is from its bytes.

The client's filename and Content-Type are only hints: they are checked
against the sniffed type, and a file whose contents belong to a different
category (e.g. a PDF named `photo.jpg`) is rejected.
"""

import io
import os
import zipfile
from dataclasses import dataclass

from apps.aiChat.attachments.errors import AttachmentError

IMAGE = "image"
AUDIO = "audio"
DOCUMENT = "document"

_EXTENSIONS = {
    IMAGE: {".jpg", ".jpeg", ".png", ".webp", ".gif", ".heic", ".heif"},
    AUDIO: {
        ".wav", ".mp3", ".m4a", ".aac", ".mp4", ".ogg", ".oga", ".opus",
        ".flac", ".webm", ".weba", ".aif", ".aiff",
    },
    DOCUMENT: {".pdf", ".txt", ".md", ".csv", ".docx", ".xlsx"},
}

# Archive limits for DOCX/XLSX (zip) inspection.
_MAX_ZIP_ENTRIES = 2000
_MAX_ZIP_UNCOMPRESSED = 100 * 1024 * 1024
_MAX_ZIP_RATIO = 200


@dataclass(frozen=True)
class DetectedFile:
    kind: str          # IMAGE | AUDIO | DOCUMENT
    mime_type: str     # sniffed type, e.g. "image/png"
    extension: str     # canonical extension for storage, e.g. ".png"


def _sniff_binary(data: bytes) -> DetectedFile | None:
    head = data[:64]
    if head.startswith(b"\xff\xd8\xff"):
        return DetectedFile(IMAGE, "image/jpeg", ".jpg")
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return DetectedFile(IMAGE, "image/png", ".png")
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return DetectedFile(IMAGE, "image/webp", ".webp")
    if head[:6] in (b"GIF87a", b"GIF89a"):
        return DetectedFile(IMAGE, "image/gif", ".gif")
    if head[4:8] == b"ftyp":
        brand = head[8:12]
        if brand in (b"heic", b"heix", b"hevc", b"heim", b"heis", b"mif1", b"msf1"):
            return DetectedFile(IMAGE, "image/heic", ".heic")
        # M4A / MP4 audio container (Flutter's AAC recorder writes this).
        return DetectedFile(AUDIO, "audio/mp4", ".m4a")
    if head[:4] == b"RIFF" and head[8:12] == b"WAVE":
        return DetectedFile(AUDIO, "audio/wav", ".wav")
    if head[:4] == b"FORM" and head[8:12] in (b"AIFF", b"AIFC"):
        return DetectedFile(AUDIO, "audio/aiff", ".aiff")
    if head.startswith(b"ID3"):
        return DetectedFile(AUDIO, "audio/mp3", ".mp3")
    if head.startswith(b"OggS"):
        return DetectedFile(AUDIO, "audio/ogg", ".ogg")
    if head.startswith(b"fLaC"):
        return DetectedFile(AUDIO, "audio/flac", ".flac")
    if head.startswith(b"\x1a\x45\xdf\xa3"):
        return DetectedFile(AUDIO, "audio/webm", ".webm")
    if len(head) >= 2 and head[0] == 0xFF:
        if (head[1] & 0xF6) == 0xF0:
            return DetectedFile(AUDIO, "audio/aac", ".aac")
        if (head[1] & 0xE0) == 0xE0:
            return DetectedFile(AUDIO, "audio/mp3", ".mp3")
    if head.startswith(b"%PDF-"):
        return DetectedFile(DOCUMENT, "application/pdf", ".pdf")
    if head.startswith(b"PK\x03\x04"):
        return _sniff_office(data)
    return None


def _sniff_office(data: bytes) -> DetectedFile:
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
        infos = archive.infolist()
    except (zipfile.BadZipFile, ValueError) as exc:
        raise AttachmentError("corrupt_document") from exc

    total = sum(info.file_size for info in infos)
    packed = max(1, sum(info.compress_size for info in infos))
    if (
        len(infos) > _MAX_ZIP_ENTRIES
        or total > _MAX_ZIP_UNCOMPRESSED
        or total / packed > _MAX_ZIP_RATIO
    ):
        raise AttachmentError("corrupt_document")

    names = {info.filename.lower() for info in infos}
    if any(name.endswith("vbaproject.bin") for name in names):
        raise AttachmentError("macro_document")
    if "word/document.xml" in names:
        return DetectedFile(
            DOCUMENT,
            "application/vnd.openxmlformats-officedocument."
            "wordprocessingml.document",
            ".docx",
        )
    if "xl/workbook.xml" in names:
        return DetectedFile(
            DOCUMENT,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ".xlsx",
        )
    raise AttachmentError("unsupported_file")


def _looks_like_text(data: bytes) -> bool:
    sample = data[:8192]
    if sample.startswith((b"\xff\xfe", b"\xfe\xff")):
        return True  # UTF-16 with BOM
    if b"\x00" in sample:
        return False
    try:
        sample.decode("utf-8")
    except UnicodeDecodeError as exc:
        # A multi-byte character cut at the sample boundary is fine.
        return exc.start >= len(sample) - 3
    return True


def safe_extension(filename: str | None) -> str:
    return os.path.splitext(os.path.basename(filename or ""))[1].lower()[:10]


def _category_of(extension: str) -> str | None:
    for kind, extensions in _EXTENSIONS.items():
        if extension in extensions:
            return kind
    return None


def detect_file(
    data: bytes,
    filename: str | None,
    declared_type: str | None,
) -> DetectedFile:
    """Return the real type of an upload or raise `AttachmentError`."""
    if not data:
        raise AttachmentError("empty_file")

    extension = safe_extension(filename)
    declared = (declared_type or "").split(";")[0].strip().lower()
    detected = _sniff_binary(data)

    if detected is None:
        if not _looks_like_text(data):
            raise AttachmentError("unsupported_file")
        if extension == ".csv" or declared in ("text/csv", "application/csv"):
            detected = DetectedFile(DOCUMENT, "text/csv", ".csv")
        elif extension in (".txt", ".md", "") or declared.startswith("text/"):
            detected = DetectedFile(DOCUMENT, "text/plain", ".txt")
        else:
            raise AttachmentError("type_mismatch")

    # The name or declared type may be imprecise within a category
    # (a PNG saved as .jpg), but never point at another category.
    by_extension = _category_of(extension)
    if by_extension and by_extension != detected.kind:
        # .mp4/.webm files may legitimately hold only audio.
        if not (detected.kind == AUDIO and extension in (".mp4", ".webm")):
            raise AttachmentError("type_mismatch")
    declared_kind = declared.split("/")[0]
    if declared_kind in (IMAGE, AUDIO) and declared_kind != detected.kind:
        raise AttachmentError("type_mismatch")
    return detected
