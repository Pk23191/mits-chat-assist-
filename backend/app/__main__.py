"""Explicit local document-ingestion command; no network endpoint is exposed."""

from __future__ import annotations

import argparse
import logging

from backend.app.config import get_settings
from backend.app.ingestion import IngestionError, ingest_sources, load_faq_file, load_pdf_file, resolve_local_document
from backend.app.logging_config import configure_logging
from backend.app.retrieval import create_retrieval_service


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest local CampusAssist documents into ChromaDB.")
    parser.add_argument("source", nargs="?", default="sample/fictional_faqs.json", help="Path relative to DATA_DIR")
    args = parser.parse_args()
    settings = get_settings()
    configure_logging(settings.log_level)
    try:
        source_path = resolve_local_document(args.source, settings.data_dir)
        if source_path.suffix.lower() == ".json" and source_path.name == "fictional_faqs.json":
            sources = load_faq_file(source_path, settings.max_document_bytes)
        elif source_path.suffix.lower() == ".pdf":
            sources = load_pdf_file(source_path, settings)
        else:
            raise IngestionError("Only the sample FAQ JSON and text-based PDF files are supported.")
        service = create_retrieval_service(settings)
        count = ingest_sources(service.vector_store, sources, settings)
        print(f"Ingested {len(sources)} source document(s) as {count} chunks.")
        return 0
    except IngestionError as exc:
        logging.getLogger(__name__).error("document_ingestion_rejected", extra={"reason": str(exc)})
        parser.error(str(exc))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
