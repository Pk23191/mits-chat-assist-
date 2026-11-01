"""Embedding-backed persistent Chroma store and retrieval service."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from langchain_core.documents import Document

from backend.app.config import Settings


class Embeddings(Protocol):
    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...
    def embed_query(self, text: str) -> list[float]: ...


@dataclass(frozen=True)
class RetrievedChunk:
    content: str
    metadata: dict[str, Any]
    distance: float


import re

CAMPUS_SYNONYMS: list[tuple[str, str]] = [
    # Admission & Documents
    (r"\b(document|documents|verification|counselling|counseling)\b", "admission procedure DTE Bhopal counselling JEE verification"),
    (r"\b(lateral entry|direct 2nd year|second year|diploma)\b", "direct second year lateral entry engineering diploma DTE"),
    (r"\b(eligibility|criteria|cutoff|cut-off|rank|opening rank)\b", "eligibility criteria JEE Main score opening rank DTE"),
    
    # Courses & Degrees
    (r"\b(course|courses|degree|degrees|program|programs|programmes|branch|branches)\b", "B.Tech M.Tech MCA Ph.D B.Arch B.Plan engineering programmes"),
    
    # Fees & Scholarships
    (r"\b(fee|fees|tuition|cost|expense)\b", "fee structure tuition hostel fee payment"),
    (r"\b(scholarship|scholarships|concession|financial aid|waiver)\b", "scholarship economically backward students MP Govt institute"),
    
    # Location & Transit
    (r"\b(reach|location|address|railway|station|bus|transport|distance)\b", "reach MITS railway station bus stand 3 km transportation facility"),
    
    # Facilities
    (r"\b(hostel|hostels|accommodation|mess)\b", "hostel facility boys girls campus accommodation"),
    (r"\b(canteen|cafeteria|food)\b", "canteen cafeteria food hostel facilities campus"),
    
    # Academics & Calendar
    (r"\b(calendar|schedule|semester|session|registration|commence|commencement)\b", "academic calendar semester registration commencement of classes"),
    (r"\b(exam|exams|test|mid sem|mid-sem|examination|midsem)\b", "mid semester test examination schedule academic calendar"),
    (r"\b(result|results|declaration)\b", "declaration of results examination academic calendar"),
    (r"\b(autonomous|autonomy|affiliat|university|aicte|ugc|nba|accredit)\b", "UGC autonomy deemed university RGPV Bhopal AICTE NBA accredited"),
    
    # Placements
    (r"\b(placement|placements|package|packages|salary|recruiter|recruiters|recruit|job)\b", "campus placement training cell highest package average package recruiters"),
    
    # History & Establishment
    (r"\b(found|founded|establish|established|inception|history|start|started)\b", "established in 1957 foundation history Madhav Institute MITS Gwalior"),
]


def expand_query(query: str) -> str:
    """Expand student query with domain-specific terminology for institutional RAG."""
    q_lower = query.lower().strip()
    expansions: list[str] = []
    for pattern, syn_terms in CAMPUS_SYNONYMS:
        if re.search(pattern, q_lower):
            expansions.append(syn_terms)
    if expansions and not re.search(r"\b(mits|madhav|gwalior)\b", q_lower):
        expansions.append("MITS Gwalior")
    if expansions:
        unique_terms = dict.fromkeys(" ".join(expansions).split())
        return f"{query} " + " ".join(unique_terms)
    return query


class EmbeddingModelError(RuntimeError):
    """Raised when the embedding model cannot be loaded or files are missing."""


def load_embeddings(settings: Settings) -> Embeddings:
    """Load the configured embedding model with offline-first precedence and actionable diagnostics."""
    import os
    from backend.app.download_model import is_model_cached_locally

    model_name = settings.embedding_model
    model_dir = settings.embedding_model_dir

    # Check if local model files or cached weights exist
    is_cached, _ = is_model_cached_locally(model_name, model_dir)

    # Respect explicit configuration or default to offline if local files exist
    if settings.hf_hub_offline is True or (settings.hf_hub_offline is None and is_cached):
        os.environ["HF_HUB_OFFLINE"] = "1"
        try:
            import huggingface_hub.constants
            huggingface_hub.constants.HF_HUB_OFFLINE = True
        except Exception:
            pass
    elif settings.hf_hub_offline is False:
        os.environ.pop("HF_HUB_OFFLINE", None)
        try:
            import huggingface_hub.constants
            huggingface_hub.constants.HF_HUB_OFFLINE = False
        except Exception:
            pass


    try:
        from langchain_huggingface import HuggingFaceEmbeddings

        effective_model = model_dir if model_dir and Path(model_dir).is_dir() else model_name
        embeddings = HuggingFaceEmbeddings(
            model_name=effective_model,
            model_kwargs={"device": "cpu"},
            encode_kwargs={"normalize_embeddings": True},
        )
        return embeddings
    except Exception as exc:
        raise EmbeddingModelError(
            f"Failed to load embedding model '{model_name}'. "
            f"If you are setting up on a new laptop or offline, run: "
            f"`python -m backend.app.download_model` to download and verify the model files. "
            f"Details: {exc}"
        ) from exc


class RetrievalService:
    """Own the embedding and Chroma configuration shared by ingestion and queries."""

    def __init__(self, settings: Settings, embeddings: Embeddings | None = None) -> None:
        import chromadb
        from langchain_chroma import Chroma

        if embeddings is None:
            embeddings = load_embeddings(settings)
            # Verify real embedding model works and produces expected dimension
            test_vec = embeddings.embed_query("CampusAssist dimension probe")
            actual_dim = len(test_vec)
            if "all-MiniLM-L6-v2" in settings.embedding_model and actual_dim != 384:
                raise RuntimeError(
                    f"Embedding dimension mismatch: expected 384 for '{settings.embedding_model}', but got {actual_dim}."
                )

        Path(settings.vector_store_dir).mkdir(parents=True, exist_ok=True)
        self.settings = settings
        self.embeddings = embeddings

        client = chromadb.PersistentClient(path=settings.vector_store_dir)
        collection = client.get_or_create_collection(
            name=settings.chroma_collection,
            metadata={"hnsw:space": "cosine", "embedding_model": settings.embedding_model},
        )
        if collection.metadata and collection.metadata.get("embedding_model") != settings.embedding_model:
            raise RuntimeError("Configured embedding model does not match the persistent collection.")
        self.vector_store = Chroma(
            client=client, collection_name=settings.chroma_collection,
            embedding_function=embeddings,
        )
        self.vector_store.get(limit=1)


    @property
    def available(self) -> bool:
        try:
            self.vector_store.get(limit=1)
            return True
        except Exception:
            return False

    def retrieve_detailed(
        self, question: str, top_k: int | None = None
    ) -> tuple[list[RetrievedChunk], int, int, float | None, float]:
        """Return (filtered_chunks, raw_count, filtered_count, best_raw_distance, threshold)."""
        query = question.strip()
        if not query or len(query) > 1000:
            raise ValueError("Question must contain between 1 and 1000 characters.")
        limit = self.settings.retrieval_top_k if top_k is None else top_k
        if limit < 1 or limit > 10:
            raise ValueError("top_k must be between 1 and 10.")

        # Calibrate threshold to safely reject out-of-domain questions while supporting valid inquiries
        calibrated_threshold = min(float(self.settings.retrieval_max_distance), 0.72)

        # Primary vector similarity search
        raw_matches: list[tuple[Document, float]] = self.vector_store.similarity_search_with_score(query, k=limit)

        # Domain-aware query expansion for natural student phrasing
        expanded_q = expand_query(query)
        if expanded_q != query:
            expanded_matches: list[tuple[Document, float]] = self.vector_store.similarity_search_with_score(expanded_q, k=limit)
            # Deduplicate by document content, retaining the minimum distance (highest relevance)
            merged: dict[str, tuple[Document, float]] = {}
            for doc, score in raw_matches + expanded_matches:
                content = doc.page_content
                sc = float(score)
                if content not in merged or sc < merged[content][1]:
                    merged[content] = (doc, sc)
            sorted_candidates = sorted(merged.values(), key=lambda x: x[1])[:limit]
        else:
            sorted_candidates = raw_matches

        raw_count = len(sorted_candidates)
        best_raw_distance = min([float(score) for _, score in sorted_candidates]) if sorted_candidates else None
        filtered = [
            RetrievedChunk(content=doc.page_content, metadata=dict(doc.metadata), distance=float(score))
            for doc, score in sorted_candidates
            if float(score) <= calibrated_threshold
        ]
        return filtered, raw_count, len(filtered), best_raw_distance, calibrated_threshold

    def retrieve(self, question: str, top_k: int | None = None) -> list[RetrievedChunk]:
        """Return relevant content and metadata without generating an answer."""
        chunks, _, _, _, _ = self.retrieve_detailed(question, top_k)
        return chunks



def create_retrieval_service(settings: Settings) -> RetrievalService:
    """Create configured local embeddings and persistent Chroma storage."""
    return RetrievalService(settings)
