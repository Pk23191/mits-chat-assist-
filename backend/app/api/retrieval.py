"""Versioned retrieval API schemas and endpoint."""

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

from backend.app.retrieval import RetrievalService

router = APIRouter(prefix="/api/v1", tags=["retrieval"])


class RetrieveRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    top_k: int | None = Field(default=None, ge=1, le=10)

    @field_validator("question")
    @classmethod
    def question_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Question cannot be blank.")
        return value.strip()


class RetrievedSource(BaseModel):
    content: str
    document_id: str
    category: str
    source_id: str
    document_name: str
    chunk_id: str
    distance: float


class RetrieveResponse(BaseModel):
    results: list[RetrievedSource]
    no_results: bool


def get_service(request: Request) -> RetrievalService:
    service = getattr(request.app.state, "retrieval_service", None)
    if service is None or not service.available:
        raise HTTPException(status_code=503, detail={"code": "retrieval_unavailable", "message": "Retrieval service is not ready."})
    return service


@router.post("/retrieve", response_model=RetrieveResponse)
def retrieve(payload: RetrieveRequest, request: Request) -> RetrieveResponse:
    service = get_service(request)
    try:
        matches = service.retrieve(payload.question, payload.top_k)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={"code": "invalid_question", "message": str(exc)}) from exc
    results: list[RetrievedSource] = []
    for match in matches:
        metadata: dict[str, Any] = match.metadata
        results.append(RetrievedSource(
            content=match.content,
            document_id=str(metadata.get("document_id", "")),
            category=str(metadata.get("category", "")),
            source_id=str(metadata.get("source_id", "")),
            document_name=str(metadata.get("document_name", "")),
            chunk_id=str(metadata.get("chunk_id", "")),
            distance=match.distance,
        ))
    return RetrieveResponse(results=results, no_results=not results)
