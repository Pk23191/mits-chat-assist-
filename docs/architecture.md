# CampusAssist AI architecture, Phase 2

```text
Fictional FAQ JSON / locally approved text PDF
                 -> validated loader -> bounded overlapping chunks
                 -> local sentence-transformer embeddings
                 -> persistent ChromaDB collection
Student question -> same embedding model -> distance-filtered retrieval
                 -> matched text chunks and source metadata (no generated answer)
```

## Boundaries

- `backend/app/config.py` validates environment configuration, including storage paths, model, size limits, chunk settings, and retrieval bounds.
- `backend/app/ingestion.py` accepts known FAQ records or an explicitly selected local PDF, extracts text, validates input, creates metadata-preserving LangChain documents, and upserts stable chunk IDs.
- `backend/app/retrieval.py` creates one local Hugging Face embedding implementation and persistent Chroma collection configuration shared by ingestion and retrieval. A stored model name mismatch fails initialization rather than silently mixing vector spaces.
- `backend/app/api/retrieval.py` validates versioned request/response models and returns source chunks only.
- `backend/app/main.py` initializes retrieval in lifespan. Failures are logged without exception details in HTTP responses; readiness accurately reports unavailable until initialized.
- `backend/app/__main__.py` is the explicit local ingestion command. No public document-write endpoint exists.
- `backend/app/fetcher.py` enforces domain allowlists (`web.mitsgwalior.in`, `www.mitsgwalior.in`, `mitsgwalior.in`), rate limits (minimum 1.0s delay), HTML and PDF text extraction, size limits, canonical URL / content-hash deduplication (`data/mits/fetch_manifest.json`), audit report logging, and produces validated `SourceDocument` instances for ingestion.
- `backend/app/fetch_mits.py` provides the authorized operator CLI interface for dry-run preview, page fetching, and direct pipeline ingestion.

## Input safety

Source paths must resolve under `DATA_DIR`. FAQ JSON size is bounded; PDF files are checked for size, suffix and PDF signature, page count, encryption and extractable text. Files are parsed as data only. Chunk size and overlap, top-k, relevance distance, bytes, and pages have validated bounds. Logging records counts rather than content. API responses do not return filesystem paths.

The FAQ dataset is explicitly fictional, including dates, fee values, schedules, and invented services. Do not use it to represent real institutional rules.

## Operational notes

The first initialization downloads the configured embedding model from Hugging Face. Store persistence is local and single-process oriented. A deployment must address authentication and authorization, storage backup and concurrency, monitoring, verified source ownership, and model supply-chain controls. PDF scanning/OCR is not supported. Gemini generation is a later phase.
