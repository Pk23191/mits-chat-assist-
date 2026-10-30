"""MITS website data fetcher — downloads public HTML pages and PDFs for ingestion."""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx
from pypdf import PdfReader

from backend.app.config import Settings
from backend.app.ingestion import IngestionError, SourceDocument

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Domain allowlist — only these are permitted
# ---------------------------------------------------------------------------
ALLOWED_DOMAINS: frozenset[str] = frozenset({
    "web.mitsgwalior.in",
    "www.mitsgwalior.in",
    "mitsgwalior.in",
})

# Default starting URLs covering key student-facing sections
DEFAULT_SEED_URLS: list[str] = [
    "https://web.mitsgwalior.in/",
    "https://web.mitsgwalior.in/index.php/sitemap",
    "https://web.mitsgwalior.in/academics/academic-calendar",
    "https://web.mitsgwalior.in/admission/ug-admissions",
    "https://web.mitsgwalior.in/admission/pg-admissions",
    "https://web.mitsgwalior.in/admission/ph-d-admission",
    "https://web.mitsgwalior.in/admission/fee-structure",
    "https://web.mitsgwalior.in/admission/faqs",
    "https://web.mitsgwalior.in/academics/courses/under-graduate",
    "https://web.mitsgwalior.in/academics/courses/post-graduate",
    "https://web.mitsgwalior.in/academics/courses/ph-d",
    "https://web.mitsgwalior.in/academics/ordinances",
    "https://web.mitsgwalior.in/life-at-mits/central-facilities/library",
    "https://web.mitsgwalior.in/life-at-mits/hostels",
    "https://web.mitsgwalior.in/about-institute/about-mits",
    "https://web.mitsgwalior.in/about-institute/vision-mission",
    "https://web.mitsgwalior.in/training-internship/about-training-internship",
    "https://web.mitsgwalior.in/training-internship/internship-policy",
    "https://web.mitsgwalior.in/training-internship/placement-records",
    "https://web.mitsgwalior.in/life-at-mits/students-grievances-counselling/grievance-ragging",
    "https://web.mitsgwalior.in/life-at-mits/anti-ragging-cell",
    "https://web.mitsgwalior.in/about-institute/policies",
    "https://web.mitsgwalior.in/admission/contact",
    "https://web.mitsgwalior.in/index.php/contact-us",
]

# Maps URL path prefixes to source categories
CATEGORY_MAP: list[tuple[str, str]] = [
    ("/admission", "admissions"),
    ("/academics/courses", "courses"),
    ("/academics/academic-calendar", "academic_calendar"),
    ("/academics/ordinances", "examinations"),
    ("/academics/departments", "departments"),
    ("/academics/quality-initiatives", "academics"),
    ("/academics", "academics"),
    ("/life-at-mits/central-facilities/library", "library"),
    ("/life-at-mits/hostels", "hostel"),
    ("/life-at-mits/central-facilities", "facilities"),
    ("/life-at-mits/students-grievances", "student_welfare"),
    ("/life-at-mits/anti-ragging", "student_welfare"),
    ("/life-at-mits/student-activities", "student_activities"),
    ("/life-at-mits", "campus_life"),
    ("/training-internship", "placements"),
    ("/innovation-research", "research"),
    ("/administration", "administration"),
    ("/about-institute", "about"),
    ("/images/sop", "sop_documents"),
    ("/images/mainmenu", "institutional_documents"),
    ("/conference", "conferences"),
    ("/index.php/notifications", "notifications"),
]

DEFAULT_REQUEST_DELAY: float = 2.0
DEFAULT_TIMEOUT: float = 30.0
MAX_URL_QUEUE: int = 500


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------
@dataclass
class FetchResult:
    """Outcome for a single URL fetch attempt."""
    url: str
    status: str  # "success", "skipped", "error", "duplicate"
    content_type: str = ""
    title: str = ""
    category: str = ""
    document_id: str = ""
    content_hash: str = ""
    error_message: str = ""
    fetched_at: str = ""
    byte_size: int = 0


@dataclass
class FetchReport:
    """Aggregated report of a fetch run."""
    started_at: str = ""
    completed_at: str = ""
    dry_run: bool = False
    total_urls: int = 0
    successful: int = 0
    skipped: int = 0
    duplicates: int = 0
    errors: int = 0
    results: list[FetchResult] = field(default_factory=list)
    items_requiring_review: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def is_allowed_domain(url: str) -> bool:
    """Check whether a URL is on the official domain allowlist."""
    try:
        parsed = urlparse(url)
        return parsed.hostname is not None and parsed.hostname in ALLOWED_DOMAINS
    except Exception:
        return False


def url_to_document_id(url: str) -> str:
    """Derive a stable, filesystem-safe document ID from a canonical URL."""
    parsed = urlparse(url)
    path = parsed.path.strip("/").replace("/", "_").replace(".", "_")
    path = re.sub(r"[^a-zA-Z0-9_-]", "_", path)
    if not path:
        path = "index"
    short_hash = hashlib.sha256(url.encode()).hexdigest()[:10]
    return f"mits-{path[:80]}-{short_hash}"


def categorise_url(url: str) -> str:
    """Map a URL to a source category using path prefix matching."""
    parsed = urlparse(url)
    path = parsed.path.lower()
    for prefix, category in CATEGORY_MAP:
        if path.startswith(prefix.lower()):
            return category
    return "general"


def content_hash(data: bytes) -> str:
    """SHA-256 hex digest for deduplication."""
    return hashlib.sha256(data).hexdigest()


def _strip_boilerplate(text: str) -> str:
    """Remove common nav/footer noise from extracted HTML text."""
    # Remove excessive whitespace runs
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


def extract_html_text(html_bytes: bytes, url: str) -> dict[str, str]:
    """Extract title and cleaned body text from an HTML page.

    Returns dict with keys: title, text, canonical_url.
    """
    from html.parser import HTMLParser

    class _Extractor(HTMLParser):
        def __init__(self) -> None:
            super().__init__()
            self.title_parts: list[str] = []
            self.text_parts: list[str] = []
            self.canonical: str = ""
            self._in_title = False
            self._skip_tags: set[str] = {"script", "style", "nav", "noscript", "svg", "head"}
            self._skip_depth = 0

        def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
            if tag in self._skip_tags:
                self._skip_depth += 1
            if tag == "title":
                self._in_title = True
            if tag == "link":
                attr_dict = dict(attrs)
                if attr_dict.get("rel") == "canonical" and attr_dict.get("href"):
                    self.canonical = attr_dict["href"]

        def handle_endtag(self, tag: str) -> None:
            if tag in self._skip_tags and self._skip_depth > 0:
                self._skip_depth -= 1
            if tag == "title":
                self._in_title = False

        def handle_data(self, data: str) -> None:
            if self._in_title:
                self.title_parts.append(data)
            elif self._skip_depth == 0:
                stripped = data.strip()
                if stripped:
                    self.text_parts.append(stripped)

    try:
        html_text = html_bytes.decode("utf-8", errors="replace")
    except Exception:
        html_text = html_bytes.decode("latin-1", errors="replace")

    extractor = _Extractor()
    try:
        extractor.feed(html_text)
    except Exception:
        pass

    title = " ".join(extractor.title_parts).strip()
    body = "\n".join(extractor.text_parts)
    body = _strip_boilerplate(body)
    canonical = extractor.canonical or url

    return {"title": title, "text": body, "canonical_url": canonical}


def extract_pdf_text(pdf_bytes: bytes, max_pages: int = 100) -> str:
    """Extract text from a PDF byte payload with validation."""
    if not pdf_bytes.startswith(b"%PDF-"):
        raise IngestionError("File does not have a valid PDF signature.")
    reader = PdfReader(BytesIO(pdf_bytes), strict=True)
    if reader.is_encrypted:
        raise IngestionError("Encrypted PDFs are not supported.")
    if len(reader.pages) == 0 or len(reader.pages) > max_pages:
        raise IngestionError("PDF page count is empty or exceeds the configured limit.")
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    if not text.strip():
        raise IngestionError("PDF contains no extractable text.")
    return text.strip()


# ---------------------------------------------------------------------------
# Manifest for deduplication and incremental fetching
# ---------------------------------------------------------------------------
def load_manifest(path: Path) -> dict[str, Any]:
    """Load the deduplication manifest from a JSON file."""
    if path.is_file():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            logger.warning("manifest_corrupted_resetting")
    return {"fetched_urls": {}, "content_hashes": {}}


def save_manifest(path: Path, manifest: dict[str, Any]) -> None:
    """Persist the deduplication manifest."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")


# ---------------------------------------------------------------------------
# Core fetcher
# ---------------------------------------------------------------------------
class MITSFetcher:
    """Fetch and validate public MITS web pages and PDFs for ingestion."""

    def __init__(
        self,
        settings: Settings,
        *,
        seed_urls: list[str] | None = None,
        request_delay: float = DEFAULT_REQUEST_DELAY,
        timeout: float = DEFAULT_TIMEOUT,
        dry_run: bool = False,
        output_dir: Path | None = None,
    ) -> None:
        self.settings = settings
        self.seed_urls = seed_urls or DEFAULT_SEED_URLS
        self.request_delay = max(request_delay, 1.0)  # enforce ≥1s
        self.timeout = timeout
        self.dry_run = dry_run
        self.output_dir = output_dir or Path(settings.data_dir) / "mits"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.manifest_path = self.output_dir / "fetch_manifest.json"
        self.manifest = load_manifest(self.manifest_path)

    def fetch_all(self) -> FetchReport:
        """Fetch every seed URL, collect results, and produce a report."""
        report = FetchReport(
            started_at=datetime.now(timezone.utc).isoformat(),
            dry_run=self.dry_run,
        )
        urls = list(dict.fromkeys(self.seed_urls))[:MAX_URL_QUEUE]
        report.total_urls = len(urls)

        for url in urls:
            result = self._fetch_single(url)
            report.results.append(result)
            if result.status == "success":
                report.successful += 1
            elif result.status == "skipped":
                report.skipped += 1
            elif result.status == "duplicate":
                report.duplicates += 1
            elif result.status == "error":
                report.errors += 1
                if "review" in result.error_message.lower() or "timeout" in result.error_message.lower():
                    report.items_requiring_review.append(url)

        report.completed_at = datetime.now(timezone.utc).isoformat()
        if not self.dry_run:
            save_manifest(self.manifest_path, self.manifest)
            self._save_report(report)

        logger.info(
            "fetch_run_completed",
            extra={
                "total": report.total_urls,
                "successful": report.successful,
                "skipped": report.skipped,
                "duplicates": report.duplicates,
                "errors": report.errors,
            },
        )
        return report

    def _fetch_single(self, url: str) -> FetchResult:
        """Fetch and validate a single URL."""
        now_iso = datetime.now(timezone.utc).isoformat()
        result = FetchResult(url=url, status="error", fetched_at=now_iso)

        # Domain check
        if not is_allowed_domain(url):
            result.status = "skipped"
            result.error_message = "Domain not in allowlist."
            return result

        # Dry-run mode
        if self.dry_run:
            result.status = "skipped"
            result.error_message = "Dry-run mode; not fetching."
            result.category = categorise_url(url)
            result.document_id = url_to_document_id(url)
            return result

        # Check if already fetched (incremental)
        if url in self.manifest.get("fetched_urls", {}):
            result.status = "duplicate"
            result.error_message = "Already fetched in a previous run."
            result.document_id = self.manifest["fetched_urls"][url].get("document_id", "")
            return result

        # Rate limit
        time.sleep(self.request_delay)

        try:
            with httpx.Client(timeout=self.timeout, follow_redirects=True) as client:
                response = client.get(
                    url,
                    headers={
                        "User-Agent": "CampusAssistBot/1.0 (educational project; +https://github.com/campusassist)",
                        "Accept": "text/html,application/xhtml+xml,application/pdf,*/*",
                    },
                )
                response.raise_for_status()
        except httpx.TimeoutException:
            result.error_message = "Request timed out; requires review."
            return result
        except httpx.HTTPStatusError as exc:
            result.error_message = f"HTTP {exc.response.status_code}"
            return result
        except httpx.RequestError as exc:
            result.error_message = f"Connection error: {type(exc).__name__}"
            return result

        body = response.content
        result.byte_size = len(body)

        # Size limit
        if result.byte_size > self.settings.max_document_bytes:
            result.error_message = "Response exceeds configured size limit."
            return result

        if result.byte_size == 0:
            result.error_message = "Empty response body."
            return result

        # Content-hash deduplication
        chash = content_hash(body)
        result.content_hash = chash
        if chash in self.manifest.get("content_hashes", {}):
            result.status = "duplicate"
            result.error_message = "Content hash matches a previously fetched document."
            result.document_id = self.manifest["content_hashes"][chash].get("document_id", "")
            return result

        # Determine content type
        ctype = response.headers.get("content-type", "").lower()
        result.content_type = ctype
        doc_id = url_to_document_id(url)
        result.document_id = doc_id
        result.category = categorise_url(url)

        try:
            if "pdf" in ctype or url.lower().endswith(".pdf"):
                text = extract_pdf_text(body, self.settings.max_pdf_pages)
                result.title = Path(urlparse(url).path).stem
                save_path = self.output_dir / f"{doc_id}.pdf"
                save_path.write_bytes(body)
            elif "html" in ctype or "text" in ctype:
                extracted = extract_html_text(body, url)
                text = extracted["text"]
                result.title = extracted["title"]
                if not text.strip():
                    result.error_message = "Page contains no extractable text."
                    return result
                save_path = self.output_dir / f"{doc_id}.txt"
                save_path.write_text(text, encoding="utf-8")
            else:
                result.status = "skipped"
                result.error_message = f"Unsupported content type: {ctype[:60]}"
                return result
        except IngestionError as exc:
            result.error_message = str(exc)
            return result
        except Exception as exc:
            result.error_message = f"Extraction failed: {type(exc).__name__}"
            return result

        result.status = "success"

        # Record in manifest
        entry = {
            "document_id": doc_id,
            "title": result.title,
            "category": result.category,
            "fetched_at": now_iso,
            "content_hash": chash,
            "byte_size": result.byte_size,
        }
        self.manifest.setdefault("fetched_urls", {})[url] = entry
        self.manifest.setdefault("content_hashes", {})[chash] = entry

        return result

    def _save_report(self, report: FetchReport) -> None:
        """Write the fetch report as a JSON file."""
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        report_path = self.output_dir / f"fetch_report_{ts}.json"
        report_path.write_text(
            json.dumps(asdict(report), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def build_source_documents(self) -> list[SourceDocument]:
        """Convert fetched data files into SourceDocument records for ingestion.

        Reads all .txt and .pdf files in the output directory and creates
        SourceDocument instances compatible with the existing pipeline.
        """
        documents: list[SourceDocument] = []
        manifest_urls = self.manifest.get("fetched_urls", {})
        # Build reverse lookup: document_id -> manifest entry + url
        id_to_entry: dict[str, dict[str, Any]] = {}
        for url, entry in manifest_urls.items():
            doc_id = entry.get("document_id", "")
            if doc_id:
                id_to_entry[doc_id] = {**entry, "url": url}

        for file_path in sorted(self.output_dir.iterdir()):
            if file_path.name.startswith("fetch_") or file_path.name == "fetch_manifest.json":
                continue
            if file_path.suffix not in (".txt", ".pdf"):
                continue

            doc_id = file_path.stem
            entry = id_to_entry.get(doc_id, {})
            category = entry.get("category", "general")
            title = entry.get("title", doc_id)
            source_url = entry.get("url", "")

            try:
                if file_path.suffix == ".txt":
                    text = file_path.read_text(encoding="utf-8")
                elif file_path.suffix == ".pdf":
                    text = extract_pdf_text(
                        file_path.read_bytes(),
                        self.settings.max_pdf_pages,
                    )
                else:
                    continue

                if not text.strip():
                    continue

                documents.append(SourceDocument(
                    document_id=doc_id,
                    category=category,
                    text=f"Title: {title}\nSource: {source_url}\n\n{text}",
                    source_id=source_url or file_path.name,
                    document_name=file_path.name,
                ))
            except Exception:
                logger.warning("source_document_skipped", extra={"file": file_path.name})
                continue

        return documents
