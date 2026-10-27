"""
Legacy media path: forward an upload to the n8n webhook.

Kept only as a temporary fallback, selected with AI_MEDIA_PIPELINE=n8n.
The URL comes from N8N_WEBHOOK_URL. Behaviour matches the previous
serializer code, except that the file is read from memory instead of
`default_storage.path()` (which remote storages don't provide).
"""

import base64
import logging

import requests

from apps.aiChat import ai_config

logger = logging.getLogger(__name__)


def send_to_n8n(
    *,
    session_id: str,
    user_id: str,
    message_type: str,
    message: str,
    file_url: str | None,
    metadata: dict,
    data: bytes | None,
) -> tuple[str, dict]:
    """Return (assistant_text, assistant_metadata); never raises."""
    payload = {
        "session_id": session_id,
        "user_id": user_id,
        "message_type": message_type,
        "message": message,
        "file_url": file_url,
        "metadata": metadata,
    }
    if data is not None:
        payload["file_base64"] = base64.b64encode(data).decode("utf-8")
        payload["file_name"] = metadata.get("original_name")
        payload["file_mime"] = metadata.get("content_type")

    try:
        response = requests.post(ai_config.n8n_webhook_url(), json=payload, timeout=30)
        response.raise_for_status()
        try:
            data_json = response.json()
        except ValueError:
            data_json = {"raw": response.text}
        text = (
            data_json.get("reply")
            or data_json.get("message")
            or str(data_json)
        ) if isinstance(data_json, dict) else str(data_json)
        return text, {"provider": "n8n", "n8n_raw": data_json}
    except Exception as exc:  # noqa: BLE001 - legacy fallback, report and continue
        logger.error(
            "n8n processing failed for chat session %s (%s).",
            session_id, type(exc).__name__,
        )
        return (
            "Sorry, I am unable to respond right now.",
            {"provider": "n8n", "error": "Chat processing failed"},
        )
