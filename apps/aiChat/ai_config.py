"""
Guru AI configuration.

Every value is read at call time from the environment (or `settings.AI`
for the model name), so tests can override them and nothing is cached at
import. Secrets are never logged or returned from here except the API key
accessor used by the Gemini clients.
"""

import os

from django.conf import settings


def _env(name: str, default: str) -> str:
    value = os.getenv(name)
    return value if value not in (None, "") else default


def _int(name: str, default: int) -> int:
    try:
        return int(_env(name, str(default)))
    except ValueError:
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(_env(name, str(default)))
    except ValueError:
        return default


def _bool(name: str, default: bool) -> bool:
    return _env(name, "true" if default else "false").strip().lower() in {
        "1", "true", "yes", "on",
    }


def _ai_settings() -> dict:
    value = getattr(settings, "AI", None)
    return value if isinstance(value, dict) else {}


# ---- Provider ---------------------------------------------------------------

def gemini_api_key() -> str:
    return _env("GEMINI_API_KEY", "")


def chat_model_name() -> str:
    """Model for answers. Same default as before (`GEMINI_MODEL`)."""
    explicit = os.getenv("GEMINI_MODEL")
    if explicit:
        return explicit
    configured = (
        _ai_settings().get("MODELS", {}).get("default", {}).get("name")
    )
    return configured or "gemini-2.5-flash"


def temperature() -> float:
    return _float("AI_TEMPERATURE", 0.2)


def model_timeout_seconds() -> int:
    return _int("AI_TIMEOUT_SECONDS", 30)


def model_max_retries() -> int:
    return _int("AI_MAX_RETRIES", 1)


def request_budget_seconds() -> int:
    """Upper bound for all model calls made while answering one message."""
    return _int("AI_REQUEST_BUDGET_SECONDS", 90)


def tts_model_name() -> str:
    return _env("AI_TTS_MODEL", "gemini-2.5-flash-preview-tts")


def tts_voice_name() -> str:
    return _env("AI_TTS_VOICE", "Kore")


def voice_reply_enabled() -> bool:
    return _bool("AI_VOICE_REPLY_ENABLED", False)


def voice_reply_max_chars() -> int:
    return _int("AI_VOICE_REPLY_MAX_CHARS", 1500)


# ---- Media pipeline ---------------------------------------------------------

def media_pipeline() -> str:
    """'native' (Django + Gemini) or 'n8n' (legacy webhook fallback)."""
    value = _env("AI_MEDIA_PIPELINE", "native").strip().lower()
    return value if value in {"native", "n8n"} else "native"


def n8n_webhook_url() -> str:
    return _env(
        "N8N_WEBHOOK_URL",
        "https://permeant-elbert-sulkier.ngrok-free.dev/webhook/chat",
    )


def chat_rate() -> str:
    """DRF throttle rate for chat-send, per user."""
    return _env("AI_CHAT_RATE", "20/min")


# ---- Upload limits ----------------------------------------------------------

def max_image_bytes() -> int:
    return _int("AI_MAX_IMAGE_MB", 8) * 1024 * 1024


def max_image_pixels() -> int:
    return _int("AI_MAX_IMAGE_PIXELS", 40_000_000)


def max_image_side() -> int:
    """Larger images are downscaled before they are sent to the model."""
    return _int("AI_MAX_IMAGE_SIDE", 3072)


def max_audio_bytes() -> int:
    return _int("AI_MAX_AUDIO_MB", 15) * 1024 * 1024


def max_audio_seconds() -> int:
    return _int("AI_MAX_AUDIO_SECONDS", 180)


def max_document_bytes() -> int:
    return _int("AI_MAX_DOCUMENT_MB", 10) * 1024 * 1024


def max_document_pages() -> int:
    return _int("AI_MAX_DOCUMENT_PAGES", 50)


def max_extracted_chars() -> int:
    return _int("AI_MAX_EXTRACTED_CHARS", 300_000)


def max_sheet_rows() -> int:
    return _int("AI_MAX_SHEET_ROWS", 2000)


def document_extract_seconds() -> int:
    return _int("AI_DOCUMENT_EXTRACT_SECONDS", 20)


def document_context_chars() -> int:
    return _int("AI_DOCUMENT_CONTEXT_CHARS", 12_000)


def max_document_chunks() -> int:
    return _int("AI_MAX_DOCUMENT_CHUNKS", 8)


def document_ocr_enabled() -> bool:
    """Scanned PDFs are read by Gemini (provider OCR) when enabled."""
    return _bool("AI_DOCUMENT_OCR_ENABLED", True)


def ocr_max_pages() -> int:
    return _int("AI_OCR_MAX_PAGES", 10)


# ---- Context and retrieval --------------------------------------------------

def history_max_messages() -> int:
    return _int("AI_HISTORY_MAX_MESSAGES", 8)


def history_max_chars() -> int:
    return _int("AI_HISTORY_MAX_CHARS", 4000)


def rag_min_score() -> float:
    return _float("AI_RAG_MIN_SCORE", 0.60)


def rag_excluded_source_prefixes() -> tuple[str, ...]:
    raw = _env("AI_RAG_EXCLUDED_SOURCE_PREFIXES", "local-test/")
    return tuple(p.strip() for p in raw.split(",") if p.strip())


def crowd_stale_minutes() -> int:
    return _int("AI_CROWD_STALE_MINUTES", 15)
