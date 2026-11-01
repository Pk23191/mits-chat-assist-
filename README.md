# CampusAssist AI

**Institutional AI Assistant & Grounded Retrieval-Augmented Generation (RAG) System** for Madhav Institute of Technology & Science (MITS), Gwalior.

CampusAssist AI provides verified, document-grounded answers to student inquiries regarding admissions, academic calendars, fee structures, courses, and campus facilities. It pairs a high-performance vector retrieval engine with dual AI generation providers (Google Gemini & Local Ollama), wrapped in an official Stitch campus web interface.

---

## Key Features

- **Document-Grounded RAG Pipeline**: All answers are synthesized strictly from official MITS documents. If information is not present in the verified documents, the system explicitly acknowledges the boundary rather than fabricating responses.
- **Two-Tier Offline-First Embedding Engine**: Uses `sentence-transformers/all-MiniLM-L6-v2` with intelligent local caching and standalone CLI preparation. Offline startup is fully supported without runtime Hugging Face connectivity.
- **Multi-Provider AI Generation**:
  - **Google Gemini**: Powered by official Google GenAI (`gemini-2.5-flash`, `gemini-2.0-flash`, `gemini-1.5-flash`).
  - **Local Ollama**: Offline, sovereign LLM inference (`minicpm-v4.6:1b`, `qwen2.5:7b`, etc.) without API costs or internet dependency.
  - **Graceful Fallback**: Automatically provides retrieved excerpts with confidence scores even if external LLM generation is unavailable.
- **Self-Seeding Knowledge Base**: ChromaDB vector store automatically initializes and self-seeds on first boot from verified institutional documents in `data/mits/`.
- **Integrated Stitch Web UI**: Single-page application featuring Chat, Document Explorer, Academic Syllabus, and Knowledge Base Admin monitoring.
- **Comprehensive Health Monitoring**: Live and ready probes (`/health/live`, `/health/ready`, `/health/vectorstore`, `/health/ai-provider`).
- **Reproducible & Cross-Platform**: Verified on Windows, macOS, Linux, and Docker containers.

---

## System Requirements

- **Python**: 3.10, 3.11, 3.12, or 3.13
- **Disk Space**: ~250MB for embedding model weights and dependencies
- **RAM**: Minimum 4GB (8GB recommended if running local Ollama models)
- **OS**: Windows 10/11, macOS (Intel/Apple Silicon), or Linux (Ubuntu, Debian, etc.)

---

## Quickstart Setup Guide

### 1. Clone the Repository

```bash
git clone https://github.com/Pk23191/mits-chat-assist-.git
cd mits-chat-assist-
```

### 2. Set Up Virtual Environment

#### On Windows (PowerShell):
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

*Note: If PowerShell blocks script execution, run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` first.*

#### On macOS / Linux:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

---

### 3. Configure Environment Variables

Copy the example configuration to create your local `.env`:

```bash
cp .env.example .env     # On macOS/Linux
# OR
Copy-Item .env.example .env   # On Windows PowerShell
```

Edit `.env` to configure your AI provider:

#### Option A: Google Gemini (Recommended for cloud inference)
1. Get a free API key from [Google AI Studio](https://aistudio.google.com/).
2. Set in `.env`:
   ```ini
   AI_PROVIDER=gemini
   GEMINI_API_KEY=your_actual_gemini_api_key_here
   LLM_MODEL=gemini-2.5-flash
   ```

#### Option B: Local Ollama (Recommended for offline / private inference)
1. Install [Ollama](https://ollama.ai/) and start the daemon.
2. Pull a lightweight model:
   ```bash
   ollama pull minicpm-v4.6:1b
   # OR
   ollama pull qwen2.5:7b
   ```
3. Set in `.env`:
   ```ini
   AI_PROVIDER=ollama
   OLLAMA_BASE_URL=http://localhost:11434
   OLLAMA_MODEL=minicpm-v4.6:1b
   ```

#### Option C: Retrieval-Only (No AI API key or local model required)
Leave `GEMINI_API_KEY=` blank. The system will retrieve relevant source documents and present verified excerpts directly.

---

### 4. Prepare the Embedding Model (Offline-First Step)

Run the standalone preparation utility to download and verify the embedding model weights:

```bash
python -m backend.app.download_model
```

To verify whether the model is already present in your local cache:
```bash
python -m backend.app.download_model --check-only
```

Once downloaded, the server operates completely offline without checking Hugging Face on startup.

---

### 5. Start the Application

```bash
python -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```

Open your browser and navigate to:
**[http://127.0.0.1:8000](http://127.0.0.1:8000)**

---

## Docker Deployment

CampusAssist AI includes a multi-stage Docker build that pre-caches embedding weights for instant container boot:

### Using Docker Compose:
```bash
docker compose up -d --build
```
Access the application at `http://localhost:8000`.

---

## Automated Testing

Run the automated test suite (80 unit & integration tests):

```bash
pytest -v
```

All standard tests use deterministic embeddings and mocked LLM calls, ensuring fast and cost-free validation in CI environments.

---

## Project Architecture

```
├── .github/workflows/ci.yml       # GitHub Actions CI workflow
├── backend/
│   └── app/
│       ├── main.py                # FastAPI app, lifespan, CORS, and static file mount
│       ├── config.py              # Pydantic Settings with .env loading and validation
│       ├── retrieval.py           # ChromaDB vector store, query expansion & embeddings
│       ├── download_model.py      # Standalone embedding model preparation tool
│       ├── generation.py          # Grounded LLM generation (Gemini & Ollama)
│       ├── ingestion.py           # Document chunking, validation, and upserts
│       ├── fetcher.py             # Official MITS domain crawler and extractor
│       ├── fetch_mits.py          # CLI tool for institutional website ingestion
│       ├── logging_config.py      # Structured JSON logging
│       └── api/
│           ├── routes.py          # Health checks (/health/live, ready, vectorstore, ai-provider)
│           ├── ask.py             # Unified RAG ask endpoint (/api/v1/ask)
│           └── retrieval.py       # Raw vector similarity endpoint (/api/v1/retrieve)
├── data/
│   ├── mits/                      # Extracted official text records and manifests
│   ├── sample/                    # Sample FAQ JSON datasets
│   └── vectorstore/               # Persistent Chroma SQLite database (git-ignored)
├── frontend/
│   └── static/
│       ├── index.html             # Single Page Application (Chat, Explorer, Admin)
│       ├── app.js                 # API communication and dynamic DOM rendering
│       └── styles.css             # Design tokens and custom UI styling
├── tests/                         # Full automated test suite (80 tests)
├── pyproject.toml                 # Packaging and pytest configuration
├── requirements.txt               # Pinned dependencies
├── Dockerfile                     # Optimized production container
└── docker-compose.yml             # Local container orchestration
```

---

## API Reference

### 1. Unified Ask Endpoint (RAG + AI Generation)
`POST /api/v1/ask`

**Request Body:**
```json
{
  "question": "What is the procedure for B.Tech admission?",
  "top_k": 4
}
```

**Response:**
```json
{
  "answer": "Admission to B.Tech programs at MITS is conducted through JEE Main and MP DTE counselling...",
  "sources": [
    {
      "title": "UG Admissions 2024",
      "url": "https://web.mitsgwalior.in/admission/ug-admissions",
      "category": "admission",
      "excerpt": "Admission to Bachelor of Technology courses is governed by...",
      "confidence": 92.4
    }
  ],
  "status": "success",
  "model": "gemini-2.5-flash",
  "grounded": true
}
```

### 2. Raw Similarity Search
`POST /api/v1/retrieve`
Returns raw matched chunks and cosine distances without LLM synthesis.

### 3. Health Probes
- `GET /health/live` — Application process liveness.
- `GET /health/ready` — Vector store and embedding initialization readiness.
- `GET /health/vectorstore` — Collection chunk count and metadata.
- `GET /health/ai-provider` — Status of active and configured AI providers.

---

## Security & Repository Hygiene

- **Zero Secrets Committed**: `.env`, API keys, and credential JSONs are strictly ignored by `.gitignore`.
- **Domain Allowlist**: Web scrapers are locked strictly to official `mitsgwalior.in` domains.
- **Path Traversal Protection**: Document ingestion safely resolves paths within `data/` and rejects escapes.
- **Persistent Data Protection**: Vector store binaries (`chroma.sqlite3`) and model caches are excluded from source control.

---

## License

MIT License. Developed for institutional academic assistance.
