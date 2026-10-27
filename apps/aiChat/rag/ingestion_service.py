
from apps.aiChat.rag.document_loader import split_document
from apps.aiChat.rag.knowledge_service import add_documents, remove_documents


def ingest_text(
    text: str,
    source: str,
    chunk_size: int = 1000,
    chunk_overlap: int = 150,
    metadata: dict | None = None,
) -> int:
    """Split a source document and store its chunks in Qdrant."""

    if not source or not source.strip():
        raise ValueError("A source identifier is required.")

    chunks = split_document(
        text,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )

    documents = [
        {
            **(metadata or {}),
            "text": chunk,
            "source": source.strip(),
        }
        for chunk in chunks
    ]

    return add_documents(documents)


def ingest_sections(
    sections: list[dict],
    source: str,
    metadata: dict,
    chunk_size: int = 1000,
    chunk_overlap: int = 150,
) -> int:
    """
    Store a document whose text is split into located sections (pages,
    sheets). Earlier chunks of the same `doc_id` are replaced, so
    re-running an ingest updates a document instead of duplicating it.
    """
    doc_id = metadata.get("doc_id")
    if not doc_id:
        raise ValueError("metadata must include a doc_id.")

    documents = []
    for section in sections:
        for chunk in split_document(
            section.get("text", ""),
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        ):
            documents.append({
                **metadata,
                "text": chunk,
                "source": source,
                "location": section.get("location", ""),
            })
    if not documents:
        return 0
    remove_documents(doc_id=doc_id)
    return add_documents(documents)
