"""Local document loading, validation, chunking, and vector-store ingestion."""

from __future__ import annotations

import json
import logging
from io import BytesIO
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from langchain_core.documents import Document
from pypdf import PdfReader

from backend.app.config import Settings

logger = logging.getLogger(__name__)


class IngestionError(ValueError):
    """Raised when a source document is invalid or cannot be processed."""


@dataclass(frozen=True)
class SourceDocument:
    document_id: str
    category: str
    text: str
    source_id: str
    document_name: str


def chunk_text(text: str, size: int, overlap: int) -> list[str]:
    """Split text into bounded, overlapping chunks, preferring word boundaries."""
    if not text.strip():
        raise IngestionError("Document contains no extractable text.")
    if size <= 0 or overlap < 0 or overlap >= size:
        raise IngestionError("Chunk size and overlap configuration is invalid.")
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            boundary = text.rfind(" ", start + size // 2, end)
            if boundary > start:
                end = boundary
        part = text[start:end].strip()
        if part:
            chunks.append(part)
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return chunks


def load_faq_file(path: Path, max_bytes: int = 5_000_000) -> list[SourceDocument]:
    """Read and validate the fictional FAQ JSON dataset."""
    try:
        if path.stat().st_size <= 0 or path.stat().st_size > max_bytes:
            raise IngestionError("FAQ dataset is empty or exceeds the configured size limit.")
        payload = json.loads(path.read_text(encoding="utf-8"))
    except IngestionError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise IngestionError("FAQ dataset could not be read or parsed.") from exc
    rows = payload.get("faqs") if isinstance(payload, dict) else None
    if not isinstance(rows, list) or not rows:
        raise IngestionError("FAQ dataset must contain a non-empty 'faqs' list.")
    sources: list[SourceDocument] = []
    seen: set[str] = set()
    for item in rows:
        if not isinstance(item, dict):
            raise IngestionError("FAQ entries must be objects.")
        required = ("document_id", "category", "question", "answer", "source_id")
        if any(not isinstance(item.get(key), str) or not item[key].strip() for key in required):
            raise IngestionError("Each FAQ requires non-empty ID, category, question, answer, and source ID.")
        if item["document_id"] in seen:
            raise IngestionError("FAQ document IDs must be unique.")
        seen.add(item["document_id"])
        sources.append(SourceDocument(
            document_id=item["document_id"], category=item["category"],
            text=f"Question: {item['question'].strip()}\nAnswer: {item['answer'].strip()}",
            source_id=item["source_id"], document_name=path.name,
        ))
    return sources


def load_pdf_file(path: Path, settings: Settings) -> list[SourceDocument]:
    """Extract text from a bounded, local PDF after validating its signature."""
    try:
        size = path.stat().st_size
        if size <= 0 or size > settings.max_document_bytes:
            raise IngestionError("PDF size is empty or exceeds the configured limit.")
        if path.suffix.lower() != ".pdf":
            raise IngestionError("Only PDF documents are supported.")
        with path.open("rb") as stream:
            data = stream.read(settings.max_document_bytes + 1)
        if len(data) > settings.max_document_bytes:
            raise IngestionError("PDF size is empty or exceeds the configured limit.")
        if not data.startswith(b"%PDF-"):
            raise IngestionError("File does not have a valid PDF signature.")
        reader = PdfReader(BytesIO(data), strict=True)
        if reader.is_encrypted:
            raise IngestionError("Encrypted PDFs are not supported.")
        if len(reader.pages) == 0 or len(reader.pages) > settings.max_pdf_pages:
            raise IngestionError("PDF page count is empty or exceeds the configured limit.")
        extracted = "\n".join(page.extract_text() or "" for page in reader.pages)
        if not extracted.strip():
            raise IngestionError("PDF contains no extractable text.")
    except IngestionError:
        raise
    except Exception as exc:
        raise IngestionError("PDF could not be safely parsed.") from exc
    return [SourceDocument(
        document_id=path.stem, category="uploaded_document", text=extracted,
        source_id=path.name, document_name=path.name,
    )]


def build_chunks(sources: list[SourceDocument], settings: Settings) -> list[Document]:
    """Convert source records into LangChain documents with traceable metadata."""
    output: list[Document] = []
    for source in sources:
        parts = chunk_text(source.text, settings.chunk_size, settings.chunk_overlap)
        for index, part in enumerate(parts):
            output.append(Document(
                page_content=part,
                metadata={
                    "document_id": source.document_id,
                    "category": source.category,
                    "source_id": source.source_id,
                    "document_name": source.document_name,
                    "chunk_id": f"{source.document_id}:{index}",
                },
            ))
    if not output:
        raise IngestionError("No document chunks were produced.")
    return output


def ingest_sources(vector_store: Any, sources: list[SourceDocument], settings: Settings) -> int:
    """Upsert chunks by stable ID, making repeated ingestion idempotent."""
    documents = build_chunks(sources, settings)
    ids = [document.metadata["chunk_id"] for document in documents]
    vector_store.add_documents(documents=documents, ids=ids)
    logger.info("documents_ingested", extra={"source_count": len(sources), "chunk_count": len(documents)})
    return len(documents)


def resolve_local_document(raw_path: str, data_dir: str) -> Path:
    """Resolve a CLI-supplied document beneath data_dir and reject traversal."""
    root = Path(data_dir).resolve()
    candidate = (root / raw_path).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise IngestionError("Document path must remain inside the configured data directory.") from exc
    if not candidate.is_file():
        raise IngestionError("Document does not exist or is not a regular file.")
    return candidate
