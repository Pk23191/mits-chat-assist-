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
        err_msg = getattr(request.app.state, "retrieval_error", None) or "retrieval_service_unavailable"
        return {"status": "not_ready", "reason": err_msg}
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
    has_gemini = bool(settings.gemini_api_key and settings.gemini_api_key.get_secret_value())

    ollama_ready = False
    try:
        import httpx
        res = httpx.get(f"{settings.ollama_base_url}/api/tags", timeout=1.0)
        ollama_ready = res.status_code == 200
    except Exception:
        ollama_ready = False

    active_provider = settings.ai_provider
    if active_provider == "auto":
        active_provider = "gemini" if has_gemini else ("ollama" if ollama_ready else "none")

    is_configured = has_gemini if active_provider == "gemini" else (ollama_ready if active_provider == "ollama" else False)

    return {
        "provider": "google-gemini" if active_provider == "gemini" else active_provider,
        "configured": is_configured,
        "status": "ready" if is_configured else "unconfigured",
        "models": ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"] if active_provider == "gemini" else [settings.ollama_model],
        "active_provider": active_provider,
        "configured_provider": settings.ai_provider,
        "gemini": {
            "configured": has_gemini,
            "status": "ready" if has_gemini else "unconfigured",
            "model": settings.llm_model,
        },
        "ollama": {
            "reachable": ollama_ready,
            "url": settings.ollama_base_url,
            "model": settings.ollama_model,
        },
    }
