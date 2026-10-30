from fastapi.testclient import TestClient
import pytest

from backend.app.ingestion import SourceDocument, ingest_sources
from backend.app.main import app
from backend.app.retrieval import RetrievalService
from tests.conftest import DeterministicEmbeddings


def seed_one(service, settings) -> None:
    ingest_sources(service.vector_store, [SourceDocument(
        document_id="faq-fees-test", category="fees",
        text="Question: What is tuition?\nAnswer: Fictional tuition costs 12 imaginary credits.",
        source_id="fictional-fees", document_name="test.json",
    )], settings)


def test_successful_retrieval_returns_relevant_metadata(retrieval_service, test_settings) -> None:
    seed_one(retrieval_service, test_settings)
    results = retrieval_service.retrieve("What is tuition?")
    assert results
    assert results[0].metadata["category"] == "fees"
    assert results[0].metadata["source_id"] == "fictional-fees"
    assert results[0].distance >= 0


@pytest.mark.parametrize("question", ["", "   ", "x" * 1001])
def test_service_rejects_empty_and_invalid_questions(retrieval_service, question) -> None:
    with pytest.raises(ValueError):
        retrieval_service.retrieve(question)


def test_no_matching_results_are_explicit(retrieval_service, test_settings) -> None:
    strict_settings = test_settings.model_copy(update={"retrieval_max_distance": 0.35})
    service = RetrievalService(strict_settings, embeddings=DeterministicEmbeddings())
    seed_one(service, strict_settings)
    assert service.retrieve("What is tuition?")
    assert service.retrieve("volcano algebra nebula") == []


def test_persistent_storage_and_model_consistency(test_settings) -> None:
    service = RetrievalService(test_settings, embeddings=DeterministicEmbeddings())
    seed_one(service, test_settings)
    reopened = RetrievalService(test_settings, embeddings=DeterministicEmbeddings())
    assert reopened.available
    assert reopened.retrieve("What is tuition?")
    changed = test_settings.model_copy(update={"embedding_model": "different-model"})
    with pytest.raises(RuntimeError, match="does not match"):
        RetrievalService(changed, embeddings=DeterministicEmbeddings())


def test_retrieval_endpoint_schema_and_validation(retrieval_service, test_settings, monkeypatch) -> None:
    seed_one(retrieval_service, test_settings)
    monkeypatch.setattr(app.state, "retrieval_service", retrieval_service, raising=False)
    monkeypatch.setattr("backend.app.main.create_retrieval_service", lambda settings: retrieval_service)
    with TestClient(app) as client:
        response = client.post("/api/v1/retrieve", json={"question": "What is tuition?"})
        assert response.status_code == 200
        body = response.json()
        assert body["no_results"] is False
        assert body["results"][0]["source_id"] == "fictional-fees"
        assert body["results"][0]["chunk_id"] == "faq-fees-test:0"
        invalid = client.post("/api/v1/retrieve", json={"question": "  "})
        assert invalid.status_code == 422
        assert invalid.json()["error"]["code"] == "validation_error"


def test_retrieval_endpoint_unavailable_error(monkeypatch) -> None:
    monkeypatch.setattr(app.state, "retrieval_service", None, raising=False)
    monkeypatch.setattr("backend.app.main.create_retrieval_service", lambda settings: None)
    with TestClient(app) as client:
        response = client.post("/api/v1/retrieve", json={"question": "Anything?"})
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "retrieval_unavailable"


def test_readiness_before_and_after_service_initialization(retrieval_service, monkeypatch) -> None:
    app.state.retrieval_service = None
    monkeypatch.setattr("backend.app.main.create_retrieval_service", lambda settings: None)
    with TestClient(app) as client:
        assert client.get("/health/ready").json() == {
            "status": "not_ready", "reason": "retrieval_service_unavailable"
        }
        app.state.retrieval_service = retrieval_service
        assert client.get("/health/ready").json() == {"status": "ready"}


def test_query_expansion_domain_synonyms() -> None:
    """Ensure student phrasing is expanded with appropriate institutional keywords."""
    from backend.app.retrieval import expand_query

    # Document verification query should expand with admission/counselling terms
    expanded = expand_query("document verification process")
    assert "admission" in expanded or "counselling" in expanded
    assert "MITS Gwalior" in expanded

    # Fee query should expand with fee structure terms
    fee_expanded = expand_query("fees for B.Tech")
    assert "fee structure" in fee_expanded or "tuition" in fee_expanded

    # Irrelevant query without domain keywords should remain untouched
    unrelated = "Recipe for chocolate cake"
    assert expand_query(unrelated) == unrelated


def test_retrieve_detailed_diagnostics(retrieval_service, test_settings) -> None:
    """Ensure retrieve_detailed provides all required diagnostic fields."""
    seed_one(retrieval_service, test_settings)
    chunks, raw_cnt, filt_cnt, best_dist, thresh = retrieval_service.retrieve_detailed("What is tuition?")
    assert len(chunks) > 0
    assert raw_cnt >= filt_cnt
    assert filt_cnt == len(chunks)
    assert best_dist is not None
    assert thresh <= 0.75


def test_irrelevant_query_returns_empty(retrieval_service, test_settings) -> None:
    """Ensure completely unrelated queries return empty chunks without false positives."""
    seed_one(retrieval_service, test_settings)
    results = retrieval_service.retrieve("quantum entanglement and dark matter")
    assert results == []

