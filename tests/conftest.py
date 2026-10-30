from __future__ import annotations

import hashlib
import re

import pytest

from backend.app.config import Settings
from backend.app.retrieval import RetrievalService


class DeterministicEmbeddings:
    """Small stable test-only embedder; it never downloads a model."""

    dimensions = 128

    def _embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        for token in re.findall(r"[a-z0-9]+", text.lower()):
            index = int.from_bytes(hashlib.sha256(token.encode()).digest()[:2], "big") % self.dimensions
            vector[index] += 1.0
        norm = sum(value * value for value in vector) ** 0.5 or 1.0
        return [value / norm for value in vector]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)


@pytest.fixture
def test_settings(tmp_path):
    return Settings(
        _env_file=None,
        data_dir=str(tmp_path / "data"),
        vector_store_dir=str(tmp_path / "chroma"),
        chunk_size=800,
        chunk_overlap=120,
        retrieval_max_distance=0.75,
    )


@pytest.fixture
def retrieval_service(test_settings):
    return RetrievalService(test_settings, embeddings=DeterministicEmbeddings())
