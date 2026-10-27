
import json
import logging
import re
from functools import lru_cache
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from apps.aiChat import ai_config

logger = logging.getLogger(__name__)


class GeminiServiceError(Exception):
    """Raised when the Gemini service cannot generate a response."""


class GeminiTimeoutError(GeminiServiceError):
    """The model did not answer within the allowed time."""


class GeminiQuotaError(GeminiServiceError):
    """The provider rejected the call because of quota or rate limits."""


@lru_cache(maxsize=8)
def _chat_model(
    model_name: str,
    api_key: str,
    timeout: int,
    max_retries: int,
    temperature: float,
    json_mode: bool,
) -> ChatGoogleGenerativeAI:
    kwargs: dict[str, Any] = {
        "model": model_name,
        "google_api_key": api_key,
        "temperature": temperature,
        "timeout": timeout,
        "max_retries": max_retries,
    }
    if json_mode:
        kwargs["response_mime_type"] = "application/json"
    return ChatGoogleGenerativeAI(**kwargs)


def _response_text(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        return "\n".join(
            block["text"].strip()
            for block in content
            if isinstance(block, dict)
            and isinstance(block.get("text"), str)
            and block["text"].strip()
        )
    return ""


def _classify(exc: Exception) -> GeminiServiceError:
    """Map provider/transport errors without leaking their details."""
    name = type(exc).__name__.lower()
    text = str(exc).lower()
    if "timeout" in name or "deadline" in name or "timed out" in text:
        return GeminiTimeoutError("Gemini did not respond in time.")
    if (
        "ratelimit" in name
        or "429" in text
        or "resource_exhausted" in text
        or "quota" in text
    ):
        return GeminiQuotaError("Gemini quota or rate limit reached.")
    return GeminiServiceError("Unable to generate a response from Gemini.")


def invoke_gemini(
    content: str | list[dict],
    *,
    system: str | None = None,
    json_mode: bool = False,
    timeout: float | None = None,
) -> str:
    """
    Send text or multimodal content blocks to Gemini and return the text.

    `content` is a string or a list of LangChain content blocks, e.g.
    `{"type": "text", "text": ...}` and
    `{"type": "image" | "audio" | "file", "base64": ..., "mime_type": ...}`.
    The actual bytes are sent inline; nothing is uploaded elsewhere.
    """
    api_key = ai_config.gemini_api_key()
    if not api_key:
        raise GeminiServiceError("Gemini API key is not configured.")

    limit = ai_config.model_timeout_seconds()
    if timeout is not None:
        if timeout <= 1:
            raise GeminiTimeoutError("No time left for another model call.")
        limit = max(1, min(limit, int(timeout)))

    model = _chat_model(
        ai_config.chat_model_name(),
        api_key,
        limit,
        ai_config.model_max_retries(),
        ai_config.temperature(),
        json_mode,
    )

    messages = []
    if system:
        messages.append(SystemMessage(content=system))
    messages.append(HumanMessage(content=content))

    try:
        reply = _response_text(model.invoke(messages).content)
    except Exception as exc:
        # Only the exception type is logged: messages may contain user data.
        logger.error("Gemini call failed (%s).", type(exc).__name__)
        raise _classify(exc) from exc

    if not reply:
        raise GeminiServiceError("Gemini returned an empty response.")
    return reply


def invoke_gemini_json(
    content: str | list[dict],
    *,
    system: str | None = None,
    timeout: float | None = None,
) -> dict:
    """Like `invoke_gemini`, but the reply must be a JSON object."""
    raw = invoke_gemini(
        content, system=system, json_mode=True, timeout=timeout,
    )
    return parse_json_object(raw)


def parse_json_object(raw: str) -> dict:
    text = raw.strip()
    fenced = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.S)
    if fenced:
        text = fenced.group(1)
    try:
        value = json.loads(text)
    except ValueError as exc:
        raise GeminiServiceError("Gemini returned invalid JSON.") from exc
    if not isinstance(value, dict):
        raise GeminiServiceError("Gemini returned unexpected JSON.")
    return value


def generate_reply(message: str) -> str:
    """
    Generate a response using Google Gemini.

    Args:
        message: Non-empty user message.

    Returns:
        The generated assistant response.

    Raises:
        ValueError: If the message is empty.
        GeminiServiceError: If Gemini configuration or execution fails.
    """
    if not isinstance(message, str) or not message.strip():
        raise ValueError("Message must be a non-empty string.")
    return invoke_gemini(message.strip())
