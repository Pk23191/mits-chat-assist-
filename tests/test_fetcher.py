"""Tests for the MITS data fetcher — all HTTP calls are mocked."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
import httpx

from backend.app.config import Settings
from backend.app.fetcher import (
    ALLOWED_DOMAINS,
    FetchReport,
    MITSFetcher,
    categorise_url,
    content_hash,
    extract_html_text,
    extract_pdf_text,
    is_allowed_domain,
    load_manifest,
    save_manifest,
    url_to_document_id,
)
from backend.app.ingestion import IngestionError, SourceDocument, ingest_sources


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def fetcher_settings(tmp_path):
    return Settings(
        _env_file=None,
        data_dir=str(tmp_path / "data"),
        vector_store_dir=str(tmp_path / "chroma"),
        chunk_size=180,
        chunk_overlap=30,
        max_document_bytes=5_000_000,
        max_pdf_pages=100,
    )


@pytest.fixture
def fetcher(fetcher_settings, tmp_path):
    return MITSFetcher(
        fetcher_settings,
        seed_urls=["https://web.mitsgwalior.in/admission/faqs"],
        request_delay=0.0,  # no delay in tests
        output_dir=tmp_path / "mits_out",
    )


MINIMAL_HTML = b"""<!doctype html>
<html lang="en">
<head><title>Test Page - MITS</title>
<link rel="canonical" href="https://web.mitsgwalior.in/test-page">
</head>
<body>
<h1>Test Content</h1>
<p>This is important admission information for students.</p>
<p>Fee structure details and academic calendar.</p>
</body>
</html>"""


MINIMAL_PDF_HEADER = b"%PDF-1.4 fake"


# ---------------------------------------------------------------------------
# Domain allowlist tests
# ---------------------------------------------------------------------------
class TestDomainAllowlist:
    def test_allowed_domains_accepted(self) -> None:
        assert is_allowed_domain("https://web.mitsgwalior.in/admission/faqs")
        assert is_allowed_domain("https://www.mitsgwalior.in/about")
        assert is_allowed_domain("https://mitsgwalior.in/")

    def test_disallowed_domains_rejected(self) -> None:
        assert not is_allowed_domain("https://evil.com/phishing")
        assert not is_allowed_domain("https://google.com")
        assert not is_allowed_domain("https://example.mitsgwalior.in.evil.com")
        assert not is_allowed_domain("")
        assert not is_allowed_domain("not-a-url")

    def test_external_subdomains_rejected(self) -> None:
        assert not is_allowed_domain("https://alumni.mitsgwalior.in/")
        assert not is_allowed_domain("https://moodle.mitsgwalior.in/")


# ---------------------------------------------------------------------------
# URL utility tests
# ---------------------------------------------------------------------------
class TestURLUtilities:
    def test_document_id_is_stable(self) -> None:
        url = "https://web.mitsgwalior.in/admission/ug-admissions"
        id1 = url_to_document_id(url)
        id2 = url_to_document_id(url)
        assert id1 == id2
        assert id1.startswith("mits-")
        assert len(id1) <= 100

    def test_different_urls_produce_different_ids(self) -> None:
        id1 = url_to_document_id("https://web.mitsgwalior.in/page1")
        id2 = url_to_document_id("https://web.mitsgwalior.in/page2")
        assert id1 != id2

    def test_category_mapping(self) -> None:
        assert categorise_url("https://web.mitsgwalior.in/admission/faqs") == "admissions"
        assert categorise_url("https://web.mitsgwalior.in/academics/courses/under-graduate") == "courses"
        assert categorise_url("https://web.mitsgwalior.in/life-at-mits/hostels") == "hostel"
        assert categorise_url("https://web.mitsgwalior.in/training-internship/placement-records") == "placements"
        assert categorise_url("https://web.mitsgwalior.in/unknown/page") == "general"


# ---------------------------------------------------------------------------
# HTML extraction tests
# ---------------------------------------------------------------------------
class TestHTMLExtraction:
    def test_extracts_title_and_text(self) -> None:
        result = extract_html_text(MINIMAL_HTML, "https://web.mitsgwalior.in/test")
        assert result["title"] == "Test Page - MITS"
        assert "admission information" in result["text"]
        assert "Fee structure" in result["text"]

    def test_extracts_canonical_url(self) -> None:
        result = extract_html_text(MINIMAL_HTML, "https://web.mitsgwalior.in/test")
        assert result["canonical_url"] == "https://web.mitsgwalior.in/test-page"

    def test_strips_script_and_style(self) -> None:
        html = b"<html><body><script>alert('xss')</script><style>.x{}</style><p>Safe text</p></body></html>"
        result = extract_html_text(html, "https://web.mitsgwalior.in/t")
        assert "alert" not in result["text"]
        assert "Safe text" in result["text"]

    def test_empty_html_returns_empty_text(self) -> None:
        result = extract_html_text(b"<html><body></body></html>", "https://web.mitsgwalior.in/t")
        assert result["text"] == ""


# ---------------------------------------------------------------------------
# PDF extraction tests
# ---------------------------------------------------------------------------
class TestPDFExtraction:
    def test_invalid_pdf_rejected(self) -> None:
        with pytest.raises(IngestionError, match="signature"):
            extract_pdf_text(b"not a pdf at all")

    def test_empty_payload_rejected(self) -> None:
        with pytest.raises(IngestionError, match="signature"):
            extract_pdf_text(b"")


# ---------------------------------------------------------------------------
# Manifest and deduplication tests
# ---------------------------------------------------------------------------
class TestManifest:
    def test_load_nonexistent_returns_empty(self, tmp_path) -> None:
        manifest = load_manifest(tmp_path / "nope.json")
        assert manifest == {"fetched_urls": {}, "content_hashes": {}}

    def test_save_and_reload(self, tmp_path) -> None:
        path = tmp_path / "manifest.json"
        data = {"fetched_urls": {"https://example.com": {"document_id": "x"}}, "content_hashes": {}}
        save_manifest(path, data)
        reloaded = load_manifest(path)
        assert reloaded["fetched_urls"]["https://example.com"]["document_id"] == "x"

    def test_corrupted_manifest_resets(self, tmp_path) -> None:
        path = tmp_path / "bad.json"
        path.write_text("{invalid json", encoding="utf-8")
        manifest = load_manifest(path)
        assert manifest == {"fetched_urls": {}, "content_hashes": {}}

    def test_content_hash_is_deterministic(self) -> None:
        data = b"test content bytes"
        assert content_hash(data) == content_hash(data)

    def test_different_content_different_hash(self) -> None:
        assert content_hash(b"content A") != content_hash(b"content B")


# ---------------------------------------------------------------------------
# Fetcher integration tests (mocked HTTP)
# ---------------------------------------------------------------------------
class TestFetcherHTTPMocked:
    def _mock_response(self, content: bytes, content_type: str = "text/html", status_code: int = 200):
        """Create a mock httpx.Response."""
        response = MagicMock(spec=httpx.Response)
        response.content = content
        response.status_code = status_code
        response.headers = {"content-type": content_type}
        response.raise_for_status = MagicMock()
        if status_code >= 400:
            response.raise_for_status.side_effect = httpx.HTTPStatusError(
                message=f"HTTP {status_code}",
                request=MagicMock(),
                response=response,
            )
        return response

    @patch("backend.app.fetcher.time.sleep")
    @patch("backend.app.fetcher.httpx.Client")
    def test_successful_html_fetch(self, mock_client_cls, mock_sleep, fetcher) -> None:
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = self._mock_response(MINIMAL_HTML)
        mock_client_cls.return_value = mock_client

        report = fetcher.fetch_all()

        assert report.successful == 1
        assert report.errors == 0
        assert report.results[0].status == "success"
        assert report.results[0].category == "admissions"
        # Verify file was saved
        saved_files = list(fetcher.output_dir.glob("*.txt"))
        assert len(saved_files) == 1

    @patch("backend.app.fetcher.time.sleep")
    @patch("backend.app.fetcher.httpx.Client")
    def test_http_error_recorded(self, mock_client_cls, mock_sleep, fetcher) -> None:
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = self._mock_response(b"Not Found", status_code=404)
        mock_client_cls.return_value = mock_client

        report = fetcher.fetch_all()
        assert report.errors == 1
        assert "404" in report.results[0].error_message

    @patch("backend.app.fetcher.time.sleep")
    @patch("backend.app.fetcher.httpx.Client")
    def test_timeout_recorded(self, mock_client_cls, mock_sleep, fetcher) -> None:
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.side_effect = httpx.TimeoutException("timed out")
        mock_client_cls.return_value = mock_client

        report = fetcher.fetch_all()
        assert report.errors == 1
        assert "timed out" in report.results[0].error_message.lower()
        assert len(report.items_requiring_review) == 1

    @patch("backend.app.fetcher.time.sleep")
    @patch("backend.app.fetcher.httpx.Client")
    def test_connection_error_recorded(self, mock_client_cls, mock_sleep, fetcher) -> None:
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.side_effect = httpx.ConnectError("connection refused")
        mock_client_cls.return_value = mock_client

        report = fetcher.fetch_all()
        assert report.errors == 1
        assert "ConnectError" in report.results[0].error_message

    @patch("backend.app.fetcher.time.sleep")
    @patch("backend.app.fetcher.httpx.Client")
    def test_oversized_response_rejected(self, mock_client_cls, mock_sleep, fetcher_settings, tmp_path) -> None:
        tiny_settings = fetcher_settings.model_copy(update={"max_document_bytes": 10})
        f = MITSFetcher(
            tiny_settings,
            seed_urls=["https://web.mitsgwalior.in/big"],
            request_delay=0.0,
            output_dir=tmp_path / "out",
        )
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = self._mock_response(b"x" * 100)
        mock_client_cls.return_value = mock_client

        report = f.fetch_all()
        assert report.errors == 1
        assert "size limit" in report.results[0].error_message.lower()

    @patch("backend.app.fetcher.time.sleep")
    @patch("backend.app.fetcher.httpx.Client")
    def test_empty_response_rejected(self, mock_client_cls, mock_sleep, fetcher) -> None:
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = self._mock_response(b"")
        mock_client_cls.return_value = mock_client

        report = fetcher.fetch_all()
        assert report.errors == 1
        assert "empty" in report.results[0].error_message.lower()

    @patch("backend.app.fetcher.time.sleep")
    @patch("backend.app.fetcher.httpx.Client")
    def test_unsupported_content_type_skipped(self, mock_client_cls, mock_sleep, fetcher) -> None:
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = self._mock_response(b"\x89PNG binary", content_type="image/png")
        mock_client_cls.return_value = mock_client

        report = fetcher.fetch_all()
        assert report.skipped == 1
        assert "unsupported" in report.results[0].error_message.lower()


class TestFetcherDisallowedDomain:
    def test_disallowed_domain_skipped(self, fetcher_settings, tmp_path) -> None:
        f = MITSFetcher(
            fetcher_settings,
            seed_urls=["https://evil.com/malware"],
            request_delay=0.0,
            output_dir=tmp_path / "out",
        )
        report = f.fetch_all()
        assert report.skipped == 1
        assert report.successful == 0
        assert "allowlist" in report.results[0].error_message.lower()

    def test_mixed_domains_only_allowed_fetched(self, fetcher_settings, tmp_path) -> None:
        f = MITSFetcher(
            fetcher_settings,
            seed_urls=[
                "https://evil.com/bad",
                "https://web.mitsgwalior.in/about-institute/about-mits",
            ],
            request_delay=0.0,
            dry_run=True,
            output_dir=tmp_path / "out",
        )
        report = f.fetch_all()
        assert report.results[0].status == "skipped"  # evil.com
        assert "allowlist" in report.results[0].error_message.lower()
        assert report.results[1].status == "skipped"  # dry-run
        assert "dry" in report.results[1].error_message.lower()


class TestFetcherDryRun:
    def test_dry_run_does_not_download(self, fetcher_settings, tmp_path) -> None:
        f = MITSFetcher(
            fetcher_settings,
            seed_urls=["https://web.mitsgwalior.in/admission/faqs"],
            request_delay=0.0,
            dry_run=True,
            output_dir=tmp_path / "out",
        )
        report = f.fetch_all()
        assert report.dry_run is True
        assert report.skipped == 1
        assert report.successful == 0
        # No files should be written
        assert not list((tmp_path / "out").glob("*.txt"))
        assert not (tmp_path / "out" / "fetch_manifest.json").exists()


class TestFetcherDuplicateDetection:
    @patch("backend.app.fetcher.time.sleep")
    @patch("backend.app.fetcher.httpx.Client")
    def test_url_duplicate_detected_on_second_run(self, mock_client_cls, mock_sleep, fetcher) -> None:
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = MagicMock(
            content=MINIMAL_HTML,
            status_code=200,
            headers={"content-type": "text/html"},
            raise_for_status=MagicMock(),
        )
        mock_client_cls.return_value = mock_client

        # First run
        report1 = fetcher.fetch_all()
        assert report1.successful == 1

        # Second run — same URL should be marked duplicate
        report2 = fetcher.fetch_all()
        assert report2.duplicates == 1
        assert report2.successful == 0

    @patch("backend.app.fetcher.time.sleep")
    @patch("backend.app.fetcher.httpx.Client")
    def test_content_hash_duplicate_detected(self, mock_client_cls, mock_sleep, fetcher_settings, tmp_path) -> None:
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = MagicMock(
            content=MINIMAL_HTML,
            status_code=200,
            headers={"content-type": "text/html"},
            raise_for_status=MagicMock(),
        )
        mock_client_cls.return_value = mock_client

        # Two different URLs with identical content
        f = MITSFetcher(
            fetcher_settings,
            seed_urls=[
                "https://web.mitsgwalior.in/page-a",
                "https://web.mitsgwalior.in/page-b",
            ],
            request_delay=0.0,
            output_dir=tmp_path / "out",
        )
        report = f.fetch_all()
        assert report.successful == 1
        assert report.duplicates == 1


class TestFetcherRateLimiting:
    @patch("backend.app.fetcher.time.sleep")
    @patch("backend.app.fetcher.httpx.Client")
    def test_rate_limiting_enforced(self, mock_client_cls, mock_sleep, fetcher_settings, tmp_path) -> None:
        f = MITSFetcher(
            fetcher_settings,
            seed_urls=["https://web.mitsgwalior.in/page1", "https://web.mitsgwalior.in/page2"],
            request_delay=2.0,
            output_dir=tmp_path / "out",
        )
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = MagicMock(
            content=MINIMAL_HTML,
            status_code=200,
            headers={"content-type": "text/html"},
            raise_for_status=MagicMock(),
        )
        mock_client_cls.return_value = mock_client

        f.fetch_all()
        # time.sleep should be called for each URL
        assert mock_sleep.call_count >= 2
        # Verify the delay is at least 1s (enforced minimum)
        for call in mock_sleep.call_args_list:
            assert call[0][0] >= 1.0

    def test_minimum_delay_enforced(self, fetcher_settings, tmp_path) -> None:
        f = MITSFetcher(
            fetcher_settings,
            seed_urls=[],
            request_delay=0.1,  # below minimum
            output_dir=tmp_path / "out",
        )
        assert f.request_delay >= 1.0


class TestBuildSourceDocuments:
    def test_builds_from_saved_files(self, fetcher_settings, tmp_path) -> None:
        out = tmp_path / "mits_out"
        out.mkdir()
        # Create a fetched text file
        doc_id = "mits-test_page-abc123"
        (out / f"{doc_id}.txt").write_text(
            "This is admission information from the MITS website.",
            encoding="utf-8",
        )
        # Create a manifest entry
        manifest = {
            "fetched_urls": {
                "https://web.mitsgwalior.in/test": {
                    "document_id": doc_id,
                    "title": "Test Page",
                    "category": "admissions",
                    "fetched_at": "2026-01-01T00:00:00Z",
                    "content_hash": "abc",
                    "byte_size": 100,
                }
            },
            "content_hashes": {},
        }
        (out / "fetch_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

        f = MITSFetcher(fetcher_settings, seed_urls=[], output_dir=out)
        sources = f.build_source_documents()

        assert len(sources) == 1
        assert sources[0].document_id == doc_id
        assert sources[0].category == "admissions"
        assert "admission information" in sources[0].text
        assert sources[0].source_id == "https://web.mitsgwalior.in/test"

    def test_skips_empty_files(self, fetcher_settings, tmp_path) -> None:
        out = tmp_path / "mits_out"
        out.mkdir()
        (out / "mits-empty-xyz.txt").write_text("", encoding="utf-8")
        (out / "fetch_manifest.json").write_text(json.dumps({"fetched_urls": {}, "content_hashes": {}}))

        f = MITSFetcher(fetcher_settings, seed_urls=[], output_dir=out)
        sources = f.build_source_documents()
        assert len(sources) == 0

    def test_ignores_report_and_manifest_files(self, fetcher_settings, tmp_path) -> None:
        out = tmp_path / "mits_out"
        out.mkdir()
        (out / "fetch_manifest.json").write_text("{}", encoding="utf-8")
        (out / "fetch_report_20260101T000000Z.json").write_text("{}", encoding="utf-8")

        f = MITSFetcher(fetcher_settings, seed_urls=[], output_dir=out)
        sources = f.build_source_documents()
        assert len(sources) == 0


class TestIngestionIntegration:
    """Verify that fetched documents feed into the existing ingestion pipeline."""

    def test_source_documents_are_ingestable(self, retrieval_service, test_settings) -> None:
        """SourceDocuments from fetcher conform to the ingestion interface."""
        sources = [
            SourceDocument(
                document_id="mits-admissions-test",
                category="admissions",
                text="Title: UG Admissions\nSource: https://web.mitsgwalior.in/admission/ug-admissions\n\nAdmissions are open for B.Tech programs.",
                source_id="https://web.mitsgwalior.in/admission/ug-admissions",
                document_name="mits-admissions-test.txt",
            ),
        ]
        count = ingest_sources(retrieval_service.vector_store, sources, test_settings)
        assert count >= 1

        # Verify retrieval works
        results = retrieval_service.retrieve("B.Tech admissions")
        assert results
        assert results[0].metadata["category"] == "admissions"
        assert results[0].metadata["source_id"] == "https://web.mitsgwalior.in/admission/ug-admissions"

    def test_duplicate_ingestion_is_idempotent(self, retrieval_service, test_settings) -> None:
        sources = [
            SourceDocument(
                document_id="mits-fees-test",
                category="admissions",
                text="Fee structure for the academic year. Total fees are listed per semester.",
                source_id="https://web.mitsgwalior.in/admission/fee-structure",
                document_name="mits-fees-test.txt",
            ),
        ]
        first = ingest_sources(retrieval_service.vector_store, sources, test_settings)
        second = ingest_sources(retrieval_service.vector_store, sources, test_settings)
        assert first == second
