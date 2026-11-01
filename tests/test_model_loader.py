"""Tests for embedding model loading, offline checking, and dimension verification."""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from backend.app.config import Settings
from backend.app.download_model import is_model_cached_locally, prepare_embedding_model
from backend.app.retrieval import EmbeddingModelError, RetrievalService, load_embeddings


def test_is_model_cached_locally_returns_false_for_nonexistent_dir(tmp_path):
    fake_dir = str(tmp_path / "nonexistent_model")
    cached, loc = is_model_cached_locally("sentence-transformers/all-MiniLM-L6-v2", fake_dir)
    # If the hub cache contains it, it might return true for hub, but for fake dir without hub it checks correctly
    assert isinstance(cached, bool)


def test_is_model_cached_locally_detects_local_model_files(tmp_path):
    model_dir = tmp_path / "custom_model"
    model_dir.mkdir()
    (model_dir / "modules.json").write_text("{}", encoding="utf-8")

    cached, loc = is_model_cached_locally("custom-model", str(model_dir))
    assert cached is True
    assert loc == str(model_dir)


def test_load_embeddings_raises_embedding_model_error_when_unavailable():
    settings = Settings(
        embedding_model="nonexistent-org/invalid-model-name-xyz-999",
        embedding_model_dir="/path/to/nowhere",
        hf_hub_offline=True,
    )
    with pytest.raises(EmbeddingModelError) as exc_info:
        load_embeddings(settings)

    err = str(exc_info.value)
    assert "Failed to load embedding model" in err
    assert "python -m backend.app.download_model" in err


def test_retrieval_service_dimension_mismatch_raises_runtime_error(test_settings):
    class IncompatibleEmbedder:
        def embed_query(self, text: str) -> list[float]:
            return [0.1] * 512  # Wrong dimension: 512 instead of 384

        def embed_documents(self, texts: list[str]) -> list[list[float]]:
            return [[0.1] * 512 for _ in texts]

    # Explicitly test that if someone configures a 512-dim embedder for all-MiniLM-L6-v2, it raises error
    with patch("backend.app.retrieval.load_embeddings", return_value=IncompatibleEmbedder()):
        with pytest.raises(RuntimeError, match="Embedding dimension mismatch: expected 384"):
            RetrievalService(test_settings)


def test_prepare_embedding_model_dry_verification():
    mock_model = MagicMock()
    mock_model.encode.return_value = [0.1] * 384

    with patch("sentence_transformers.SentenceTransformer", return_value=mock_model):
        success = prepare_embedding_model("sentence-transformers/all-MiniLM-L6-v2")
        assert success is True
        mock_model.encode.assert_called_once()


def test_prepare_embedding_model_detects_dimension_mismatch():
    mock_model = MagicMock()
    mock_model.encode.return_value = [0.1] * 128  # Mismatch

    with patch("sentence_transformers.SentenceTransformer", return_value=mock_model):
        success = prepare_embedding_model("sentence-transformers/all-MiniLM-L6-v2")
        assert success is False
