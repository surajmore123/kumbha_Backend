"""
Storage for chat files and document extracts.

Files are written through `default_storage` under `chat/<user_id>/` with
random names (never the client's filename), so paths are not guessable
and nothing relies on `default_storage.path()`, which remote storages do
not implement. Every read checks that the key belongs to the requesting
user, so one user's files can never be loaded into another user's chat.
"""

import json
import uuid

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage


def _prefix(user_id) -> str:
    return f"chat/{user_id}/"


def owns(user_id, key: str | None) -> bool:
    return (
        isinstance(key, str)
        and key.startswith(_prefix(user_id))
        and ".." not in key
    )


def save_bytes(user_id, data: bytes, extension: str, folder: str = "") -> str:
    """Save and return the storage key."""
    sub = f"{folder.strip('/')}/" if folder else ""
    key = f"{_prefix(user_id)}{sub}{uuid.uuid4().hex}{extension}"
    return default_storage.save(key, ContentFile(data))


def url_for(key: str) -> str:
    return default_storage.url(key)


def load_bytes(user_id, key: str, max_bytes: int) -> bytes | None:
    if not owns(user_id, key) or not default_storage.exists(key):
        return None
    with default_storage.open(key, "rb") as handle:
        data = handle.read(max_bytes + 1)
    return data if len(data) <= max_bytes else None


def save_json(user_id, value: dict, folder: str) -> str:
    data = json.dumps(value, ensure_ascii=False).encode("utf-8")
    return save_bytes(user_id, data, ".json", folder)


def load_json(user_id, key: str, max_bytes: int = 5 * 1024 * 1024) -> dict | None:
    data = load_bytes(user_id, key, max_bytes)
    if data is None:
        return None
    try:
        value = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def delete(key: str) -> None:
    if key and default_storage.exists(key):
        default_storage.delete(key)
