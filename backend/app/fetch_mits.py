"""CLI command to fetch MITS public pages and ingest them into ChromaDB.

Usage:
    python -m backend.app.fetch_mits                # fetch + ingest
    python -m backend.app.fetch_mits --dry-run      # preview only
    python -m backend.app.fetch_mits --fetch-only   # fetch without ingesting
    python -m backend.app.fetch_mits --ingest-only  # ingest previously fetched files
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import asdict

from backend.app.config import get_settings
from backend.app.fetcher import MITSFetcher, FetchReport
from backend.app.ingestion import ingest_sources, IngestionError
from backend.app.logging_config import configure_logging
from backend.app.retrieval import create_retrieval_service


def _print_report(report: FetchReport) -> None:
    """Print a human-readable summary of the fetch run."""
    print("\n--- MITS Fetch Report ---")
    print(f"  Started:    {report.started_at}")
    print(f"  Completed:  {report.completed_at}")
    print(f"  Dry run:    {report.dry_run}")
    print(f"  Total URLs: {report.total_urls}")
    print(f"  Successful: {report.successful}")
    print(f"  Skipped:    {report.skipped}")
    print(f"  Duplicates: {report.duplicates}")
    print(f"  Errors:     {report.errors}")
    if report.items_requiring_review:
        print(f"  Requires review: {len(report.items_requiring_review)}")
        for url in report.items_requiring_review:
            print(f"    - {url}")
    print()
    for r in report.results:
        status_icon = {"success": "+", "skipped": "-", "duplicate": "=", "error": "x"}.get(r.status, "?")
        line = f"  [{status_icon}] [{r.status:>9}] {r.url[:90]}"
        if r.error_message:
            line += f"  ({r.error_message[:60]})"
        print(line)
    print("--- End of Report ---\n")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fetch public MITS Gwalior pages and ingest into the CampusAssist vector store.",
    )
    parser.add_argument("--dry-run", action="store_true", help="List URLs without downloading")
    parser.add_argument("--fetch-only", action="store_true", help="Download pages but do not ingest")
    parser.add_argument("--ingest-only", action="store_true", help="Ingest previously downloaded pages")
    parser.add_argument("--delay", type=float, default=2.0, help="Seconds between requests (min 1.0)")
    parser.add_argument("--timeout", type=float, default=30.0, help="HTTP request timeout in seconds")
    parser.add_argument("--url", action="append", dest="urls", help="Add a specific URL (repeatable)")
    args = parser.parse_args()

    if args.fetch_only and args.ingest_only:
        parser.error("--fetch-only and --ingest-only are mutually exclusive.")

    settings = get_settings()
    configure_logging(settings.log_level)
    logger = logging.getLogger(__name__)

    fetcher = MITSFetcher(
        settings,
        seed_urls=args.urls if args.urls else None,
        request_delay=args.delay,
        timeout=args.timeout,
        dry_run=args.dry_run,
    )

    # --- Fetch phase ---
    if not args.ingest_only:
        print(f"Fetching MITS pages (delay={fetcher.request_delay}s, dry_run={args.dry_run})...")
        report = fetcher.fetch_all()
        _print_report(report)

        if args.dry_run:
            print("Dry run complete. No files were downloaded or ingested.")
            return 0

        if report.errors > 0 and report.successful == 0:
            print("All fetch attempts failed. Nothing to ingest.", file=sys.stderr)
            return 1

    # --- Ingest phase ---
    if not args.fetch_only:
        try:
            sources = fetcher.build_source_documents()
            if not sources:
                print("No source documents found to ingest.")
                return 0

            print(f"Building retrieval service and ingesting {len(sources)} source documents...")
            service = create_retrieval_service(settings)
            count = ingest_sources(service.vector_store, sources, settings)
            print(f"Ingested {len(sources)} MITS source document(s) as {count} chunks.")
        except IngestionError as exc:
            logger.error("mits_ingestion_rejected", extra={"reason": str(exc)})
            print(f"Ingestion error: {exc}", file=sys.stderr)
            return 1
        except Exception as exc:
            logger.exception("mits_ingestion_failed")
            print(f"Ingestion failed: {type(exc).__name__}", file=sys.stderr)
            return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
