# CampusAssist AI

CampusAssist AI is a fictional college FAQ retrieval project. Phase 2 adds local document ingestion, chunking, embeddings, persistent ChromaDB storage, and source-grounded retrieval. It does not generate answers with Gemini. The sample FAQs, policies, dates, and all sample fee amounts are invented and are not verified information about any real college.

## Requirements and Windows setup

Use Python 3.11 or newer and PowerShell from the repository root:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

If PowerShell blocks activation, run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` in that terminal, then activate again. The first embedding-model initialization downloads `sentence-transformers/all-MiniLM-L6-v2` from Hugging Face and stores it in the local model cache. That model is used for both ingestion and retrieval. No Gemini API key is required in this phase.

## Configuration

Settings come from environment variables or `.env`; `.env` must not be committed. Configure `CORS_ORIGINS` as an exact comma-separated allowlist. Retrieval settings:

| Variable | Default | Purpose |
| --- | --- | --- |
| `DATA_DIR` | `data` | Root for approved local source documents |
| `VECTOR_STORE_DIR` | `data/vectorstore` | Persistent local Chroma storage |
| `CHROMA_COLLECTION` | `campusassist_faq` | Chroma collection name |
| `EMBEDDING_MODEL` | `sentence-transformers/all-MiniLM-L6-v2` | Local embedding model; must remain consistent with the stored collection |
| `CHUNK_SIZE` / `CHUNK_OVERLAP` | `800` / `120` | Character chunking limits |
| `RETRIEVAL_TOP_K` | `4` | Default result count (hard maximum 10) |
| `RETRIEVAL_MAX_DISTANCE` | `0.75` | Maximum cosine distance accepted as relevant |
| `MAX_DOCUMENT_BYTES` | `5000000` | Source file size limit |
| `MAX_PDF_PAGES` | `100` | PDF page count limit |

## Ingest the fictional sample FAQs

Run ingestion as a local operator command. It is intentionally not exposed as an HTTP upload route:

```powershell
python -m backend.app
```

To ingest a text-based PDF saved under `DATA_DIR`:

```powershell
python -m backend.app sample/handbook.pdf
```

The source path is resolved beneath `DATA_DIR`; traversal outside it is rejected. Only the fixed fictional FAQ JSON or a PDF is accepted. The PDF reader validates file signature, byte and page limits, encryption state, and extractable text. Scanned/image-only PDFs are unsupported. Re-ingestion upserts deterministic chunk IDs.

## Fetch and ingest MITS Gwalior public pages

An auditable data-fetching pipeline downloads permitted public HTML pages and PDF documents from the official Madhav Institute of Technology & Science (MITS) website (`web.mitsgwalior.in`), extracts structured text and metadata, and feeds validated documents into the ingestion pipeline:

```powershell
# 1. Preview URLs without downloading (dry run)
python -m backend.app.fetch_mits --dry-run

# 2. Fetch permitted public pages and ingest into ChromaDB
python -m backend.app.fetch_mits

# 3. Fetch specific URLs with conservative rate limiting (minimum 1.0s delay)
python -m backend.app.fetch_mits --url https://web.mitsgwalior.in/admission/ug-admissions --delay 2.0

# 4. Ingest previously fetched documents
python -m backend.app.fetch_mits --ingest-only
```

### Safety and auditing rules
- **Domain allowlist**: Requests are strictly restricted to `web.mitsgwalior.in`, `www.mitsgwalior.in`, and `mitsgwalior.in`. External subdomains and external links are rejected.
- **Rate limiting and timeouts**: Enforces a minimum 1.0s delay between requests (default 2.0s) and configurable HTTP timeout (default 30.0s).
- **Deduplication**: Tracks canonical URLs and SHA-256 content hashes in `data/mits/fetch_manifest.json` to prevent re-downloading duplicate documents.
- **Audit reports**: Generates a timestamped JSON report in `data/mits/fetch_report_<timestamp>.json` detailing successes, skips, duplicates, errors, and items requiring human review.
- **No public crawling endpoint**: Fetching requires explicit CLI invocation; no unauthenticated HTTP endpoint can trigger crawling.

## Run the service and retrieve

```powershell
python -m uvicorn backend.app.main:app --reload
```

`GET /health/live` checks process liveness. `GET /health/ready` reports whether the local embedding model and persistent vector store initialized. Retrieval is `POST /api/v1/retrieve`:

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/v1/retrieve `
  -ContentType 'application/json' `
  -Body '{"question":"What is the fictional library schedule?","top_k":3}'
```

The response contains matching text chunks, source identifiers, category, document and chunk IDs, and Chroma cosine distance. `no_results` is true when the collection is empty or every match exceeds the configured distance threshold. This endpoint returns sources only; it does not generate an answer.

## Tests

```powershell
python -m pytest
```

Tests use temporary Chroma directories and deterministic test embeddings. They do not download an embedding model or call a live API.

## Structure

- `backend/app/config.py`: validated environment settings
- `backend/app/ingestion.py`: FAQ/PDF reading, validation, chunking, stable metadata and upserts
- `backend/app/retrieval.py`: local embedding model and persistent Chroma service
- `backend/app/api/`: health and versioned retrieval routes/schemas
- `data/sample/fictional_faqs.json`: clearly labeled fictional examples
- `frontend/static/`: future browser interface; contains no credentials
- `tests/`: deterministic ingestion, retrieval, API and health tests
- `docs/architecture.md`: phase architecture and security notes

## Limitations

This is a local development foundation. Model initialization requires a one-time model download and may take time; readiness remains false when initialization fails. PDF text extraction does not OCR scanned pages. The local store is not designed as a shared or production database. No authentication, Gemini answer generation, authorization workflow, or deployment configuration is included. Real policies must be supplied and verified by an authorized institution before this can answer real student questions.
