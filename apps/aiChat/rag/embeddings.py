import os

from langchain_google_genai import GoogleGenerativeAIEmbeddings


def get_embeddings() -> GoogleGenerativeAIEmbeddings:
    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not configured.")

    model = os.getenv(
        "GEMINI_EMBEDDING_MODEL",
        "gemini-embedding-001",
    )

    return GoogleGenerativeAIEmbeddings(
        model=model,
        google_api_key=api_key,
    )