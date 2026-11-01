"""CampusAssist AI FastAPI application."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from fastapi.staticfiles import StaticFiles

from backend.app.api.routes import router
from backend.app.config import get_settings
from backend.app.logging_config import configure_logging
from backend.app.retrieval import create_retrieval_service
from backend.app.api.retrieval import router as retrieval_router
from backend.app.api.ask import router as ask_router

settings = get_settings()
configure_logging(settings.log_level)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    logger.info("application_started", extra={"environment": settings.app_env})
    try:
        service = create_retrieval_service(settings)
        # Resilient self-seeding: if vector store has 0 chunks on boot, populate from approved knowledge base
        try:
            chunk_count = service.vector_store._collection.count() if hasattr(service.vector_store, "_collection") else 0
            if chunk_count == 0:
                mits_dir = Path(settings.data_dir) / "mits"
                if mits_dir.is_dir():
                    from backend.app.fetcher import MITSFetcher
                    from backend.app.ingestion import ingest_sources

                    fetcher = MITSFetcher(settings)
                    sources = fetcher.build_source_documents()
                    if sources:
                        ingested = ingest_sources(service.vector_store, sources, settings)
                        logger.info("knowledge_base_auto_seeded", extra={"chunks": ingested})
        except Exception:
            logger.warning("knowledge_base_auto_seed_skipped")
        _.state.retrieval_service = service
        _.state.retrieval_error = None
        logger.info("retrieval_service_initialized")
    except Exception as exc:
        _.state.retrieval_service = None
        _.state.retrieval_error = str(exc)
        logger.exception("retrieval_service_initialization_failed: %s", exc)
    yield
    logger.info("application_stopped")


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.state.retrieval_service = None
app.state.retrieval_error = None

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization"],
)
app.include_router(router)
app.include_router(retrieval_router)
app.include_router(ask_router)

# Mount Stitch frontend static files — must come after API routers
_static_dir = Path(__file__).resolve().parent.parent.parent / "frontend" / "static"
if _static_dir.is_dir():
    app.mount("/", StaticFiles(directory=str(_static_dir), html=True), name="static")


@app.exception_handler(RequestValidationError)
async def validation_error_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    """Return a stable, non-sensitive validation error envelope."""
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "validation_error",
                "message": "Request validation failed.",
                "details": jsonable_encoder(exc.errors()),
            }
        },
    )


@app.exception_handler(StarletteHTTPException)
async def http_error_handler(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Return the shared error envelope for application HTTP errors."""
    detail = exc.detail if isinstance(exc.detail, dict) else {}
    return JSONResponse(
        status_code=exc.status_code,
        headers=exc.headers,
        content={"error": {
            "code": str(detail.get("code", "http_error")),
            "message": str(detail.get("message", "The request could not be completed.")),
        }},
    )


@app.exception_handler(Exception)
async def unexpected_error_handler(_: Request, exc: Exception) -> JSONResponse:
    """Log unexpected failures and avoid leaking internals to clients."""
    logger.exception("unhandled_application_error", exc_info=exc)
    return JSONResponse(
        status_code=500,
        content={"error": {"code": "internal_server_error", "message": "An unexpected error occurred."}},
    )
