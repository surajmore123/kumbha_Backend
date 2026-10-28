"""
Audio validation and preparation for speech understanding.

Gemini accepts WAV, MP3, AIFF, AAC, OGG and FLAC directly. M4A/MP4 and
WebM are converted with the existing ffmpeg helper
(`utils.audio.convert_audio_to_mp3`) only when ffmpeg is available;
otherwise they are rejected with a clear message rather than sent in a
format the model may not read.

Decodability and duration are checked with Python's `wave` module for PCM
WAV and with ffprobe for other formats when it is installed. Silent PCM
WAV recordings are detected locally; for other formats the transcription
step reports when no speech was heard.
"""

import io
import os
import shutil
import subprocess
import tempfile
import wave
from array import array
from dataclasses import dataclass

from apps.aiChat import ai_config
from apps.aiChat.attachments.errors import AttachmentError
from utils import audio as audio_utils

DIRECT_TYPES = {
    "audio/wav", "audio/mp3", "audio/aiff", "audio/aac", "audio/ogg",
    "audio/flac",
}
CONVERTED_TYPES = {"audio/mp4", "audio/webm"}

# Peak amplitude (16-bit) below which a PCM recording counts as silence.
_SILENCE_PEAK = 300


@dataclass(frozen=True)
class PreparedAudio:
    data: bytes
    mime_type: str
    extension: str
    duration_seconds: float | None
    converted: bool


def ffmpeg_path() -> str | None:
    path = audio_utils.FFMPEG_PATH
    if path and (os.path.isfile(path) or shutil.which(path)):
        return path
    return None


def ffprobe_path() -> str | None:
    configured = os.getenv("FFPROBE_PATH")
    if configured and os.path.isfile(configured):
        return configured
    ffmpeg = ffmpeg_path()
    if ffmpeg and os.path.isfile(ffmpeg):
        folder, name = os.path.split(ffmpeg)
        sibling = os.path.join(folder, name.replace("ffmpeg", "ffprobe"))
        if os.path.isfile(sibling):
            return sibling
    return shutil.which("ffprobe")


def _wav_info(data: bytes) -> tuple[float, bool] | None:
    """(duration, silent) for PCM WAV, or None when `wave` can't read it."""
    try:
        with wave.open(io.BytesIO(data)) as wav:
            frames = wav.getnframes()
            rate = wav.getframerate()
            width = wav.getsampwidth()
            pcm = wav.readframes(frames)
    except (wave.Error, EOFError):
        return None
    if frames == 0 or rate == 0 or not pcm:
        raise AttachmentError("empty_audio")
    duration = frames / rate
    silent = False
    if width == 2:
        samples = array("h")
        samples.frombytes(pcm[: len(pcm) - len(pcm) % 2])
        silent = max((abs(s) for s in samples), default=0) < _SILENCE_PEAK
    return duration, silent


def _probe_duration(path: str) -> float | None:
    """Duration via ffprobe; raises `corrupt_audio` if it can't decode."""
    ffprobe = ffprobe_path()
    if not ffprobe:
        return None
    try:
        result = subprocess.run(
            [
                ffprobe, "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                path,
            ],
            capture_output=True,
            timeout=20,
            check=True,
        )
    except subprocess.TimeoutExpired as exc:
        raise AttachmentError("corrupt_audio") from exc
    except subprocess.CalledProcessError as exc:
        raise AttachmentError("corrupt_audio") from exc
    try:
        return float(result.stdout.decode().strip())
    except ValueError:
        return None


def prepare_audio(data: bytes, mime_type: str) -> PreparedAudio:
    if not data:
        raise AttachmentError("empty_audio")
    if len(data) > ai_config.max_audio_bytes():
        raise AttachmentError(
            "file_too_large", limit=ai_config.max_audio_bytes() // (1024 * 1024),
        )
    if mime_type not in DIRECT_TYPES | CONVERTED_TYPES:
        raise AttachmentError("unsupported_file")

    max_seconds = ai_config.max_audio_seconds()
    extension = {
        "audio/wav": ".wav", "audio/mp3": ".mp3", "audio/aiff": ".aiff",
        "audio/aac": ".aac", "audio/ogg": ".ogg", "audio/flac": ".flac",
        "audio/mp4": ".m4a", "audio/webm": ".webm",
    }[mime_type]

    if mime_type == "audio/wav":
        info = _wav_info(data)
        if info is not None:
            duration, silent = info
            if silent:
                raise AttachmentError("silent_audio")
            if duration > max_seconds:
                raise AttachmentError("audio_too_long", limit=max_seconds)
            return PreparedAudio(data, mime_type, extension, duration, False)

    needs_conversion = mime_type in CONVERTED_TYPES
    if needs_conversion and not ffmpeg_path():
        raise AttachmentError("audio_conversion_unavailable")

    with tempfile.TemporaryDirectory(prefix="guru_audio_") as folder:
        source = os.path.join(folder, "input" + extension)
        with open(source, "wb") as handle:
            handle.write(data)

        duration = _probe_duration(source)
        if duration is not None:
            if duration <= 0.05:
                raise AttachmentError("empty_audio")
            if duration > max_seconds:
                raise AttachmentError("audio_too_long", limit=max_seconds)

        if not needs_conversion:
            return PreparedAudio(data, mime_type, extension, duration, False)

        try:
            converted_path = audio_utils.convert_audio_to_mp3(source)
            with open(converted_path, "rb") as handle:
                converted = handle.read()
        except (RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
            raise AttachmentError("corrupt_audio") from exc

    if not converted:
        raise AttachmentError("corrupt_audio")
    return PreparedAudio(converted, "audio/mp3", ".mp3", duration, True)
