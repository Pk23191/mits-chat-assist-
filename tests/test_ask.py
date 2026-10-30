"""Tests for the /api/v1/ask endpoint and answer generation module."""

from fastapi.testclient import TestClient
import pytest
from unittest.mock import patch

from backend.app.api.ask import AskRequest
from backend.app.generation import GeneratedAnswer, generate_answer
from backend.app.ingestion import SourceDocument, ingest_sources
from backend.app.main import app


def seed_test_doc(service, settings) -> None:
    ingest_sources(
        service.vector_store,
        [
            SourceDocument(
                document_id="faq-ug-admissions",
                category="admissions",
                text="MITS Gwalior offers 14 B.Tech engineering programs accredited by NBA. Admission is through JEE Main and MP DTE counselling.",
                source_id="https://web.mitsgwalior.in/admission/ug-admissions",
                document_name="UG Admissions 2024",
            )
        ],
        settings,
    )


def test_ask_endpoint_schema_validation() -> None:
    """Test AskRequest validation for empty and oversized questions."""
    with pytest.raises(ValueError):
        AskRequest(question="")

    with pytest.raises(ValueError):
        AskRequest(question="   ")

    with pytest.raises(ValueError):
        AskRequest(question="x" * 1001)

    req = AskRequest(question="What are B.Tech programs?", top_k=3)
    assert req.question == "What are B.Tech programs?"
    assert req.top_k == 3


def test_ask_endpoint_retrieval_unavailable(monkeypatch) -> None:
    """When retrieval service is None or unavailable, ask returns 503."""
    monkeypatch.setattr(app.state, "retrieval_service", None, raising=False)
    monkeypatch.setattr("backend.app.main.create_retrieval_service", lambda settings: None)
    with TestClient(app) as client:
        response = client.post("/api/v1/ask", json={"question": "What is MITS?"})
        assert response.status_code == 503
        data = response.json()
        assert data["error"]["code"] == "retrieval_unavailable"


def test_ask_endpoint_success_with_mocked_gemini(retrieval_service, test_settings, monkeypatch) -> None:
    """When retrieval succeeds and Gemini generates an answer, return success response."""
    seed_test_doc(retrieval_service, test_settings)
    monkeypatch.setattr(app.state, "retrieval_service", retrieval_service, raising=False)
    monkeypatch.setattr("backend.app.main.create_retrieval_service", lambda settings: retrieval_service)

    mock_answer = GeneratedAnswer(
        answer="MITS offers 14 B.Tech programs through JEE Main counselling.",
        model="gemini-3.8-flash",
        grounded=True,
    )

    with patch("backend.app.api.ask.generate_answer", return_value=mock_answer):
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/ask",
                json={"question": "What B.Tech courses are offered?"},
            )
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "success"
            assert data["grounded"] is True
            assert "14 B.Tech" in data["answer"]
            assert len(data["sources"]) > 0
            assert data["sources"][0]["category"] == "admissions"
            assert "https://web.mitsgwalior.in" in data["sources"][0]["url"]


def test_ask_endpoint_fallback_when_gemini_fails(retrieval_service, test_settings, monkeypatch) -> None:
    """When Gemini raises RuntimeError, endpoint gracefully falls back to retrieval_only."""
    seed_test_doc(retrieval_service, test_settings)
    monkeypatch.setattr(app.state, "retrieval_service", retrieval_service, raising=False)
    monkeypatch.setattr("backend.app.main.create_retrieval_service", lambda settings: retrieval_service)

    with patch("backend.app.api.ask.generate_answer", side_effect=RuntimeError("API unreachable")):
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/ask",
                json={"question": "What B.Tech courses are offered?"},
            )
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "retrieval_only"
            assert data["grounded"] is False
            assert len(data["sources"]) > 0


def test_generation_empty_chunks(test_settings) -> None:
    """When retrieved chunks are empty, generate_answer returns grounded=False notice without calling Gemini."""
    from pydantic import SecretStr
    settings_with_key = test_settings.model_copy(update={"gemini_api_key": SecretStr("test-key")})
    result = generate_answer("What is tuition?", [], settings_with_key)
    assert result.grounded is False
    assert "couldn't find any relevant documents" in result.answer
    assert result.model == "none"


def test_generation_missing_api_key(test_settings) -> None:
    """When gemini_api_key is None, generate_answer raises RuntimeError."""
    no_key_settings = test_settings.model_copy(update={"gemini_api_key": None})
    with pytest.raises(RuntimeError, match="GEMINI_API_KEY is not configured"):
        generate_answer("What is MITS?", [{"content": "MITS doc"}], no_key_settings)
