
import uuid
from typing import Any

from django.utils import timezone
from qdrant_client import models

from apps.aiChat import ai_config
from apps.aiChat.rag.embeddings import get_embeddings
from apps.aiChat.rag.vector_store import (
    COLLECTION_NAME,
    ensure_collection,
    qdrant_session,
)

# Provenance kept with every chunk. `verification_status` is one of
# "verified" (a person checked it against the issuing authority and named
# the evidence), "unverified" or "test" (synthetic local data, never used
# in answers).
METADATA_FIELDS = (
    "doc_id",
    "title",
    "organization",
    "source_url",
    "publication_date",
    "effective_date",
    "ingested_at",
    "verification_status",
    "verified_by",
    "version",
    "location",
    "language",
)
VERIFICATION_STATUSES = ("verified", "unverified", "test")


def add_documents(documents: list[dict[str, Any]]) -> int:
    """
    Add prepared document chunks.

    Each document must contain 'text' and 'source'; any of
    METADATA_FIELDS may be added. Returns the number of stored chunks.
    """
    valid_documents = [
        doc for doc in documents
        if str(doc.get("text", "")).strip()
        and str(doc.get("source", "")).strip()
    ]

    if not valid_documents:
        return 0

    texts = [doc["text"].strip() for doc in valid_documents]
    # Embed before opening the store: the API call is the slow part.
    vectors = get_embeddings().embed_documents(texts)
    ingested_at = timezone.now().isoformat()

    points = []

    for doc, text, vector in zip(valid_documents, texts, vectors):
        point_id = str(
            uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"{doc['source']}:{doc.get('location', '')}:{text}",
            )
        )
        payload = {"text": text, "source": doc["source"]}
        for name in METADATA_FIELDS:
            if doc.get(name) not in (None, ""):
                payload[name] = doc[name]
        payload.setdefault("ingested_at", ingested_at)
        payload.setdefault("verification_status", "unverified")

        points.append(
            models.PointStruct(id=point_id, vector=vector, payload=payload)
        )

    with qdrant_session() as client:
        ensure_collection(client)
        client.upsert(collection_name=COLLECTION_NAME, points=points, wait=True)

    return len(points)


def is_trusted_payload(payload: dict) -> bool:
    """Synthetic/test chunks are never used to answer pilgrims."""
    if payload.get("verification_status") == "test":
        return False
    source = str(payload.get("source", ""))
    return not source.startswith(ai_config.rag_excluded_source_prefixes())


def search_documents(
    question: str,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Retrieve the most relevant stored document chunks."""
    if not question.strip():
        return []

    if not 1 <= limit <= 20:
        raise ValueError("limit must be between 1 and 20")

    query_vector = get_embeddings().embed_query(question)

    with qdrant_session() as client:
        if not client.collection_exists(COLLECTION_NAME):
            return []
        # Over-fetch, because test records are filtered out afterwards.
        results = client.query_points(
            collection_name=COLLECTION_NAME,
            query=query_vector,
            limit=min(limit * 3, 60),
            with_payload=True,
            query_filter=models.Filter(
                must_not=[
                    models.FieldCondition(
                        key="verification_status",
                        match=models.MatchValue(value="test"),
                    )
                ]
            ),
        )

    found = []
    for point in results.points:
        payload = point.payload or {}
        if not (
            isinstance(payload.get("text"), str)
            and isinstance(payload.get("source"), str)
            and is_trusted_payload(payload)
        ):
            continue
        found.append({
            "text": payload["text"],
            "source": payload["source"],
            "score": point.score,
            "metadata": {
                name: payload[name] for name in METADATA_FIELDS if name in payload
            },
        })
        if len(found) >= limit:
            break
    return found


def _source_filter(doc_id: str | None = None, source: str | None = None):
    conditions = []
    if doc_id:
        conditions.append(
            models.FieldCondition(key="doc_id", match=models.MatchValue(value=doc_id))
        )
    if source:
        conditions.append(
            models.FieldCondition(key="source", match=models.MatchValue(value=source))
        )
    if not conditions:
        raise ValueError("A doc_id or source is required.")
    return models.Filter(must=conditions)


def remove_documents(doc_id: str | None = None, source: str | None = None) -> int:
    """Delete every chunk of one document. Returns how many were removed."""
    selector = _source_filter(doc_id, source)
    with qdrant_session() as client:
        if not client.collection_exists(COLLECTION_NAME):
            return 0
        count = client.count(COLLECTION_NAME, count_filter=selector, exact=True).count
        if count:
            client.delete(
                collection_name=COLLECTION_NAME,
                points_selector=models.FilterSelector(filter=selector),
                wait=True,
            )
    return count


def set_verification_status(status: str, source_prefix: str) -> int:
    """Re-label chunks (e.g. mark synthetic ones as 'test'); nothing is deleted."""
    if status not in VERIFICATION_STATUSES:
        raise ValueError(f"status must be one of {VERIFICATION_STATUSES}")
    with qdrant_session() as client:
        ids = [
            point.id
            for point in _scroll_all(client)
            if str((point.payload or {}).get("source", "")).startswith(source_prefix)
        ]
        if ids:
            client.set_payload(
                collection_name=COLLECTION_NAME,
                payload={"verification_status": status},
                points=ids,
                wait=True,
            )
    return len(ids)


def _scroll_all(client, batch: int = 256) -> list:
    if not client.collection_exists(COLLECTION_NAME):
        return []
    points, offset = [], None
    while True:
        page, offset = client.scroll(
            COLLECTION_NAME, limit=batch, offset=offset, with_payload=True,
            with_vectors=False,
        )
        points.extend(page)
        if offset is None:
            return points


def iterate_points(batch: int = 256) -> list:
    """Every stored chunk (payloads only)."""
    with qdrant_session() as client:
        return _scroll_all(client, batch)
