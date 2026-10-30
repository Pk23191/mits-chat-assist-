"""Health and landing-page routes."""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from backend.app.retrieval import RetrievalService

router = APIRouter()


from pathlib import Path

_index_file = Path(__file__).resolve().parent.parent.parent.parent / "frontend" / "static" / "index.html"


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
def home() -> HTMLResponse:
    """Return the integrated Stitch frontend if present, otherwise minimal landing page."""
    if _index_file.is_file():
        return HTMLResponse(content=_index_file.read_text(encoding="utf-8"))
    return HTMLResponse(content="<!doctype html><html lang='en'><meta charset='utf-8'><title>CampusAssist AI</title><body><h1>CampusAssist AI</h1><p>College FAQ assistant foundation is running.</p></body></html>")


@router.get("/health/live")
def live() -> dict[str, str]:
    """Confirm that the process is responding."""
    return {"status": "live"}


@router.get("/health/ready")
def ready(request: Request) -> dict[str, str]:
    """Report whether embeddings and the persistent vector store initialized."""
    service: RetrievalService | None = getattr(request.app.state, "retrieval_service", None)
    if service is None or not service.available:
        return {"status": "not_ready", "reason": "retrieval_service_unavailable"}
    return {"status": "ready"}


@router.get("/health/vectorstore")
def health_vectorstore(request: Request) -> dict[str, object]:
    """Report vector store collection health and document count."""
    from backend.app.config import get_settings

    service: RetrievalService | None = getattr(request.app.state, "retrieval_service", None)
    if service is None or not service.available:
        return {"status": "not_ready", "reason": "vectorstore_unavailable"}

    settings = get_settings()
    chunk_count = 0
    try:
        if hasattr(service.vector_store, "_collection"):
            chunk_count = service.vector_store._collection.count()
    except Exception:
        chunk_count = -1

    return {
        "status": "ready",
        "collection": settings.chroma_collection,
        "chunk_count": chunk_count,
        "embedding_model": settings.embedding_model,
    }


@router.get("/health/ai-provider")
def health_ai_provider() -> dict[str, object]:
    """Report AI provider status without exposing secrets or making expensive generation calls."""
    from backend.app.config import get_settings

    settings = get_settings()
    has_key = bool(settings.gemini_api_key and settings.gemini_api_key.get_secret_value())
    return {
        "provider": "google-gemini",
        "configured": has_key,
        "status": "ready" if has_key else "unconfigured",
        "models": ["gemini-3.5-flash-lite", "gemini-3.8-flash", "gemini-3.5-flash"],
    }

