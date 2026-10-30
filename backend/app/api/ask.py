"""Unified ask endpoint: retrieves relevant chunks then generates a grounded answer."""

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

from backend.app.config import get_settings
from backend.app.generation import generate_answer
from backend.app.retrieval import RetrievalService

router = APIRouter(prefix="/api/v1", tags=["ask"])


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    top_k: int | None = Field(default=None, ge=1, le=10)

    @field_validator("question")
    @classmethod
    def question_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Question cannot be blank.")
        return value.strip()


class SourceCitation(BaseModel):
    title: str
    url: str
    category: str
    excerpt: str
    confidence: float


class AskResponse(BaseModel):
    answer: str
    sources: list[SourceCitation]
    status: str
    model: str
    grounded: bool


def _get_service(request: Request) -> RetrievalService:
    service = getattr(request.app.state, "retrieval_service", None)
    if service is None or not service.available:
        raise HTTPException(
            status_code=503,
            detail={"code": "retrieval_unavailable", "message": "Retrieval service is not ready."},
        )
    return service


logger = logging.getLogger(__name__)


@router.post("/ask", response_model=AskResponse)
def ask(payload: AskRequest, request: Request) -> AskResponse:
    """Retrieve relevant MITS documents and generate a grounded answer."""
    service = _get_service(request)
    settings = get_settings()

    # Step 1: Retrieve relevant chunks from ChromaDB
    try:
        matches, raw_count, filtered_count, best_raw_distance, threshold = service.retrieve_detailed(
            payload.question, payload.top_k
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "invalid_question", "message": str(exc)},
        ) from exc

    # Build chunk dicts for the generation module
    chunk_dicts: list[dict[str, Any]] = []
    sources: list[SourceCitation] = []
    for match in matches:
        meta = match.metadata
        chunk_dicts.append({
            "content": match.content,
            "source_id": str(meta.get("source_id", "")),
            "document_name": str(meta.get("document_name", "")),
            "category": str(meta.get("category", "")),
            "document_id": str(meta.get("document_id", "")),
        })
        # Compute confidence as percentage (1.0 - cosine_distance) * 100, clamped
        confidence = max(0.0, min(100.0, (1.0 - match.distance) * 100))
        sources.append(SourceCitation(
            title=str(meta.get("document_name", "Unknown Document")),
            url=str(meta.get("source_id", "")),
            category=str(meta.get("category", "general")),
            excerpt=match.content[:200] + ("..." if len(match.content) > 200 else ""),
            confidence=round(confidence, 1),
        ))

    # Step 2: Generate answer using Gemini (if configured)
    llm_attempted = False
    sanitized_error: str | None = None

    if not matches:
        # Retrieval returned 0 documents passing the threshold
        logger.info(
            "ask_pipeline_diagnostics",
            extra={
                "question_length": len(payload.question),
                "raw_chunks_count": raw_count,
                "filtered_chunks_count": filtered_count,
                "best_raw_distance": round(best_raw_distance, 4) if best_raw_distance is not None else None,
                "threshold": threshold,
                "llm_attempted": False,
                "sanitized_generation_error": None,
                "sources_count": 0,
            },
        )
        return AskResponse(
            answer="I couldn't find any relevant documents in the MITS knowledge base to answer your question. Please try rephrasing, or contact the relevant MITS department directly.",
            sources=[],
            status="no_sources_found",
            model="none",
            grounded=False,
        )

    llm_attempted = True
    try:
        result = generate_answer(payload.question, chunk_dicts, settings)
        logger.info(
            "ask_pipeline_diagnostics",
            extra={
                "question_length": len(payload.question),
                "raw_chunks_count": raw_count,
                "filtered_chunks_count": filtered_count,
                "best_raw_distance": round(best_raw_distance, 4) if best_raw_distance is not None else None,
                "threshold": threshold,
                "llm_attempted": True,
                "sanitized_generation_error": None,
                "sources_count": len(sources),
            },
        )
        return AskResponse(
            answer=result.answer,
            sources=sources,
            status="success",
            model=result.model,
            grounded=result.grounded,
        )
    except RuntimeError as exc:
        sanitized_error = f"{type(exc).__name__}: {str(exc)[:100]}"
        logger.warning(
            "ask_pipeline_diagnostics",
            extra={
                "question_length": len(payload.question),
                "raw_chunks_count": raw_count,
                "filtered_chunks_count": filtered_count,
                "best_raw_distance": round(best_raw_distance, 4) if best_raw_distance is not None else None,
                "threshold": threshold,
                "llm_attempted": True,
                "sanitized_generation_error": sanitized_error,
                "sources_count": len(sources),
            },
        )
        fallback_answer = (
            "Here are the most relevant excerpts from official MITS documents. "
            "(AI-generated summary is currently unavailable.)\n\n"
            + "\n\n".join(
                f"**{s.title}** ({s.category}):\n{s.excerpt}"
                for s in sources[:4]
            )
        )
        return AskResponse(
            answer=fallback_answer,
            sources=sources,
            status="retrieval_only",
            model="none",
            grounded=False,
        )

