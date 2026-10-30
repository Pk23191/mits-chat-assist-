import json
from pathlib import Path

import pytest

from backend.app.ingestion import (
    IngestionError,
    build_chunks,
    chunk_text,
    ingest_sources,
    load_faq_file,
    load_pdf_file,
    resolve_local_document,
)


SAMPLE = Path("data/sample/fictional_faqs.json")


def test_fictional_faq_dataset_loads_all_categories() -> None:
    sources = load_faq_file(SAMPLE)
    assert len(sources) == 16
    assert {"admissions", "courses", "fees", "library", "hostel", "examinations", "scholarships", "placements"} <= {
        source.category for source in sources
    }


def test_chunking_preserves_source_metadata(test_settings) -> None:
    sources = load_faq_file(SAMPLE)
    docs = build_chunks(sources[:1], test_settings)
    assert docs
    assert docs[0].metadata == {
        "document_id": "faq-admissions-001",
        "category": "admissions",
        "source_id": "fictional-admissions-handbook-v1",
        "document_name": "fictional_faqs.json",
        "chunk_id": "faq-admissions-001:0",
    }


def test_chunking_rejects_invalid_limits() -> None:
    with pytest.raises(IngestionError):
        chunk_text("some content", 5, 5)
    with pytest.raises(IngestionError):
        chunk_text("  ", 20, 2)


def test_faq_ingestion_and_repeat_is_idempotent(retrieval_service, test_settings) -> None:
    sources = load_faq_file(SAMPLE)
    first_count = ingest_sources(retrieval_service.vector_store, sources, test_settings)
    second_count = ingest_sources(retrieval_service.vector_store, sources, test_settings)
    assert first_count == second_count == 16
    assert len(retrieval_service.vector_store.get()["ids"]) == 16


def test_empty_and_malformed_faq_files_are_rejected(tmp_path) -> None:
    empty = tmp_path / "empty.json"
    empty.write_text("", encoding="utf-8")
    with pytest.raises(IngestionError):
        load_faq_file(empty)
    malformed = tmp_path / "malformed.json"
    malformed.write_text(json.dumps({"faqs": [{"document_id": "x"}]}), encoding="utf-8")
    with pytest.raises(IngestionError):
        load_faq_file(malformed)


def test_faq_document_size_limit(tmp_path) -> None:
    file_path = tmp_path / "large.json"
    file_path.write_text(json.dumps({"faqs": []}), encoding="utf-8")
    with pytest.raises(IngestionError, match="size limit"):
        load_faq_file(file_path, max_bytes=1)


def test_path_traversal_is_rejected(tmp_path) -> None:
    with pytest.raises(IngestionError, match="inside"):
        resolve_local_document("../outside.pdf", str(tmp_path / "data"))


def test_invalid_and_oversized_pdf_rejected(tmp_path, test_settings) -> None:
    invalid = tmp_path / "invalid.pdf"
    invalid.write_bytes(b"not a pdf")
    with pytest.raises(IngestionError, match="signature"):
        load_pdf_file(invalid, test_settings)
    oversized = tmp_path / "large.pdf"
    oversized.write_bytes(b"%PDF-" + b"0" * 100)
    tiny_settings = test_settings.model_copy(update={"max_document_bytes": 10})
    with pytest.raises(IngestionError, match="size"):
        load_pdf_file(oversized, tiny_settings)
