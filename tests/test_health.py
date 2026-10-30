from fastapi.testclient import TestClient

from backend.app.main import app

client = TestClient(app)


def test_liveness_endpoint() -> None:
    response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "live"}


def test_readiness_reports_rag_not_configured() -> None:
    response = client.get("/health/ready")
    assert response.status_code == 200
    assert response.json() == {
        "status": "not_ready",
        "reason": "retrieval_service_unavailable",
    }


def test_home_endpoint() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "CampusAssist AI" in response.text
    assert "MITS Gwalior Portal" in response.text

    app_js = client.get("/app.js")
    assert app_js.status_code == 200
    assert "submitQuery" in app_js.text

    styles = client.get("/styles.css")
    assert styles.status_code == 200


def test_ai_provider_health_endpoint() -> None:
    response = client.get("/health/ai-provider")
    assert response.status_code == 200
    data = response.json()
    assert data["provider"] == "google-gemini"
    assert "configured" in data
    assert "status" in data
    assert "models" in data
    # Verify strict secret protection
    assert "api_key" not in data
    assert "secret" not in data
    assert "gemini_api_key" not in data


def test_vectorstore_health_endpoint_when_not_ready() -> None:
    response = client.get("/health/vectorstore")
    assert response.status_code == 200
    assert response.json() == {
        "status": "not_ready",
        "reason": "vectorstore_unavailable",
    }

