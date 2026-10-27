
import os
import time
from contextlib import contextmanager
from functools import lru_cache

from django.conf import settings
from qdrant_client import QdrantClient, models

COLLECTION_NAME = "kumbh_knowledge"
VECTOR_SIZE = 3072

# How long to wait for another process to release the local store.
_LOCK_WAIT_SECONDS = 10


def _local_path() -> str:
    path = os.getenv("QDRANT_LOCAL_PATH", "./data/qdrant")
    # Resolve relative paths from the project, not the working directory.
    if not os.path.isabs(path):
        path = os.path.join(str(settings.BASE_DIR), path)
    return os.path.normpath(path)


@lru_cache(maxsize=1)
def _server_client() -> QdrantClient:
    return QdrantClient(
        url=os.environ["QDRANT_URL"],
        api_key=os.getenv("QDRANT_API_KEY") or None,
        timeout=10,
    )


@contextmanager
def qdrant_session():
    """
    A Qdrant client for one operation.

    With QDRANT_URL set, a shared client for a Qdrant server (needed for
    several workers at once). Otherwise the local store in
    QDRANT_LOCAL_PATH, opened only for the operation and closed again:
    local mode locks its folder, so holding it open would block every
    other process (other gunicorn workers, `manage.py knowledge_base`).
    """
    if os.getenv("QDRANT_URL"):
        yield _server_client()
        return

    deadline = time.monotonic() + _LOCK_WAIT_SECONDS
    while True:
        try:
            client = QdrantClient(path=_local_path())
            break
        except RuntimeError as exc:
            if "already accessed" not in str(exc) or time.monotonic() > deadline:
                raise
            time.sleep(0.2)
    try:
        yield client
    finally:
        client.close()


def ensure_collection(client: QdrantClient) -> None:
    """Create the knowledge collection if it doesn't exist."""
    if client.collection_exists(COLLECTION_NAME):
        info = client.get_collection(COLLECTION_NAME)
        size = info.config.params.vectors.size

        if size != VECTOR_SIZE:
            raise RuntimeError(
                f"Collection has vector size {size}; "
                f"expected {VECTOR_SIZE}."
            )
        return

    client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=models.VectorParams(
            size=VECTOR_SIZE,
            distance=models.Distance.COSINE,
        ),
    )
