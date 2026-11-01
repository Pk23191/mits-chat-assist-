"""Tests for multi-provider generation (Gemini, Ollama, auto fallback)."""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch
from pydantic import SecretStr

from backend.app.config import Settings
from backend.app.generation import (
    GeneratedAnswer,
    _build_context_block,
    _generate_with_ollama,
    generate_answer,
)


def test_build_context_block_formatting():
    chunks = [
        {
            "source_id": "https://web.mitsgwalior.in/admissions",
            "document_name": "Admissions 2024",
            "category": "admission",
            "content": "B.Tech requires JEE Main.",
        },
        {
            "source_id": "https://web.mitsgwalior.in/fees",
            "document_name": "Fee Schedule",
            "category": "finance",
            "content": "Tuition is payable per semester.",
        },
    ]
    block = _build_context_block(chunks)
    assert "--- Source 1 ---" in block
    assert "Document: Admissions 2024" in block
    assert "URL: https://web.mitsgwalior.in/admissions" in block
    assert "--- Source 2 ---" in block
    assert "Document: Fee Schedule" in block


def test_generate_with_ollama_success():
    settings = Settings(
        ai_provider="ollama",
        ollama_base_url="http://mock-ollama:11434",
        ollama_model="qwen2.5:7b",
    )

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "response": "According to Source 1, B.Tech admission is based on JEE Main."
    }

    with patch("httpx.post", return_value=mock_resp) as mock_post:
        res = _generate_with_ollama("How to get admission?", "doc content", settings)
        assert res.grounded is True
        assert res.model == "ollama/qwen2.5:7b"
        assert "JEE Main" in res.answer
        mock_post.assert_called_once()


def test_generate_with_ollama_http_error():
    settings = Settings(
        ai_provider="ollama",
        ollama_base_url="http://mock-ollama:11434",
        ollama_model="nonexistent-model",
    )

    mock_resp = MagicMock()
    mock_resp.status_code = 404
    mock_resp.text = "model not found"

    with patch("httpx.post", return_value=mock_resp):
        with pytest.raises(RuntimeError, match="Ollama returned HTTP 404"):
            _generate_with_ollama("Test question", "doc content", settings)


def test_generate_answer_auto_selects_ollama_when_no_gemini_key():
    settings = Settings(
        ai_provider="auto",
        gemini_api_key=None,
        ollama_base_url="http://mock-ollama:11434",
        ollama_model="qwen2.5:7b",
    )

    mock_tags = MagicMock(status_code=200)
    mock_gen = MagicMock(
        status_code=200,
        json=lambda: {"response": "Auto-routed to Ollama response."},
    )

    def mock_httpx_post(*args, **kwargs):
        return mock_gen

    def mock_httpx_get(*args, **kwargs):
        return mock_tags

    with patch("httpx.get", side_effect=mock_httpx_get), patch("httpx.post", side_effect=mock_httpx_post):
        res = generate_answer("What is the fee?", [{"content": "Fee is 50000"}], settings)
        assert res.grounded is True
        assert res.model == "ollama/qwen2.5:7b"
        assert "Auto-routed to Ollama" in res.answer


def test_generate_answer_unknown_provider_raises():
    settings = Settings(ai_provider="unsupported-provider")
    with pytest.raises(RuntimeError, match="Unknown AI provider"):
        generate_answer("Hello", [{"content": "test"}], settings)
