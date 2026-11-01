"""Standalone utility to download, cache, and verify embedding models for CampusAssist AI."""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

# Ensure project root is in sys.path
_project_root = Path(__file__).resolve().parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from backend.app.config import get_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("download_model")

EXPECTED_DIMENSIONS: dict[str, int] = {
    "sentence-transformers/all-MiniLM-L6-v2": 384,
    "all-MiniLM-L6-v2": 384,
    "sentence-transformers/all-mpnet-base-v2": 768,
}


def is_model_cached_locally(model_name: str, local_dir: str | None = None) -> tuple[bool, str]:
    """Check if the embedding model exists in a local directory or the Hugging Face Hub cache."""
    # 1. Check local directory if provided
    if local_dir:
        path = Path(local_dir)
        if path.is_dir() and any(path.glob("*.bin")) or any(path.glob("*.safetensors")):
            return True, str(path)
        if (path / "modules.json").is_file():
            return True, str(path)

    # 2. Check Hugging Face hub cache
    try:
        from huggingface_hub.constants import HUGGINGFACE_HUB_CACHE
        # Standard folder format in hub cache: models--sentence-transformers--all-MiniLM-L6-v2
        escaped_name = f"models--{model_name.replace('/', '--')}"
        hub_path = Path(HUGGINGFACE_HUB_CACHE) / escaped_name
        if hub_path.is_dir():
            snapshots = hub_path / "snapshots"
            if snapshots.is_dir() and any(snapshots.iterdir()):
                return True, str(hub_path)
    except Exception:
        pass

    return False, ""


def prepare_embedding_model(
    model_name: str,
    target_dir: str | None = None,
    verify_dimension: bool = True,
) -> bool:
    """Download and verify the sentence transformer model."""
    logger.info("Checking embedding model: %s", model_name)

    is_cached, cache_loc = is_model_cached_locally(model_name, target_dir)
    if is_cached:
        logger.info("Found cached model locally at: %s", cache_loc)
    else:
        logger.info("Model not found in local cache. Initiating download from Hugging Face Hub...")

    try:
        from sentence_transformers import SentenceTransformer

        save_path = target_dir if target_dir else None

        # Download / load model
        model = SentenceTransformer(model_name)

        if save_path:
            out_path = Path(save_path)
            out_path.mkdir(parents=True, exist_ok=True)
            logger.info("Saving model weights to local directory: %s", out_path)
            model.save(str(out_path))

        if verify_dimension:
            test_phrase = "CampusAssist AI embedding verification test query."
            embedding = model.encode(test_phrase)
            dim = len(embedding)
            expected_dim = EXPECTED_DIMENSIONS.get(model_name)

            logger.info("Generated test embedding successfully. Vector dimension: %d", dim)
            if expected_dim is not None and dim != expected_dim:
                logger.error(
                    "Dimension mismatch! Expected %d, but got %d for model '%s'",
                    expected_dim, dim, model_name
                )
                return False

        logger.info("SUCCESS: Embedding model '%s' is ready for offline operation.", model_name)
        return True

    except Exception as exc:
        logger.exception("Failed to prepare embedding model '%s': %s", model_name, exc)
        return False


def main() -> None:
    settings = get_settings()
    parser = argparse.ArgumentParser(description="Prepare and verify embedding models for CampusAssist AI")
    parser.add_argument(
        "--model",
        default=settings.embedding_model,
        help="Embedding model identifier (default: %(default)s)",
    )
    parser.add_argument(
        "--target-dir",
        default=settings.embedding_model_dir,
        help="Optional local directory to save model weights to",
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Check if model is present without downloading",
    )

    args = parser.parse_args()

    if args.check_only:
        cached, loc = is_model_cached_locally(args.model, args.target_dir)
        if cached:
            print(f"AVAILABLE: Model '{args.model}' is available at: {loc}")
            sys.exit(0)
        else:
            print(f"MISSING: Model '{args.model}' is not available in local cache.")
            sys.exit(1)

    success = prepare_embedding_model(args.model, args.target_dir)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
