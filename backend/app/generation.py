"""Multi-provider answer generation grounded in retrieved MITS documents (Gemini and Ollama)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from backend.app.config import Settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are CampusAssist AI, the official academic assistant for Madhav Institute of Technology & Science (MITS), Gwalior.

RULES:
1. Answer ONLY using the provided source documents. Do not invent policies, dates, fees, eligibility criteria, or deadlines.
2. If the provided documents do not contain enough information to answer, say so clearly and suggest the student contact the relevant MITS office.
3. Be concise, helpful, and student-friendly. Use bullet points or numbered lists for clarity when appropriate.
4. Always reference which source document(s) your answer is based on.
5. Never fabricate URLs, phone numbers, email addresses, or faculty names that are not in the sources.
6. Respond in English. If the question is in Hindi or Hinglish, respond in simple English.
"""


@dataclass(frozen=True)
class GeneratedAnswer:
    answer: str
    model: str
    grounded: bool


def _build_context_block(retrieved_chunks: list[dict[str, Any]]) -> str:
    context_parts: list[str] = []
    for i, chunk in enumerate(retrieved_chunks, 1):
        source_id = chunk.get("source_id", "Unknown source")
        doc_name = chunk.get("document_name", "Unknown document")
        category = chunk.get("category", "general")
        content = chunk.get("content", "")
        context_parts.append(
            f"--- Source {i} ---\n"
            f"Document: {doc_name}\n"
            f"Category: {category}\n"
            f"URL: {source_id}\n"
            f"Content:\n{content}\n"
        )
    return "\n".join(context_parts)


def _generate_with_gemini(
    question: str,
    context_block: str,
    settings: Settings,
) -> GeneratedAnswer:
    api_key = settings.gemini_api_key
    if api_key is None or not api_key.get_secret_value():
        raise RuntimeError("GEMINI_API_KEY is not configured in environment or .env file.")

    import socket

    # Avoid Windows IPv6 connection stalling
    orig_getaddrinfo = socket.getaddrinfo

    def _ipv4_first_getaddrinfo(host: Any, port: Any, family: int = 0, type: int = 0, proto: int = 0, flags: int = 0) -> Any:
        try:
            return orig_getaddrinfo(host, port, socket.AF_INET, type, proto, flags)
        except Exception:
            return orig_getaddrinfo(host, port, family, type, proto, flags)

    socket.getaddrinfo = _ipv4_first_getaddrinfo

    import google.generativeai as genai

    genai.configure(api_key=api_key.get_secret_value(), transport="rest")

    user_prompt = (
        f"Based on the following official MITS documents, answer the student's question.\n\n"
        f"DOCUMENTS:\n{context_block}\n\n"
        f"STUDENT QUESTION: {question}\n\n"
        f"Answer (grounded in the documents above):"
    )

    # Valid candidate models in fallback order
    preferred = settings.llm_model.strip() if settings.llm_model else "gemini-3.5-flash"
    candidates: list[str] = [preferred]
    for fallback in ["gemini-3.5-flash", "gemini-3.8-flash"]:
        if fallback not in candidates:
            candidates.append(fallback)


    last_exc: Exception | None = None
    for model_name in candidates:
        try:
            model = genai.GenerativeModel(
                model_name,
                system_instruction=SYSTEM_PROMPT,
            )
            response = model.generate_content(
                user_prompt,
                generation_config=genai.types.GenerationConfig(
                    max_output_tokens=1024,
                    temperature=0.3,
                ),
                request_options={"timeout": 15.0},
            )
            answer_text = response.text.strip() if response.text else ""
            if not answer_text:
                answer_text = "I was unable to generate an answer. Please try rephrasing your question."

            logger.info("gemini_answer_generated", extra={"model": model_name, "question_length": len(question), "answer_length": len(answer_text)})
            return GeneratedAnswer(answer=answer_text, model=model_name, grounded=True)
        except Exception as exc:
            logger.warning("gemini_model_failed (%s): %s", model_name, exc)
            last_exc = exc

    raise RuntimeError(f"Gemini answer generation failed across all candidate models: {last_exc}")


def _generate_with_ollama(
    question: str,
    context_block: str,
    settings: Settings,
) -> GeneratedAnswer:
    import httpx

    user_prompt = (
        f"Based on the following official MITS documents, answer the student's question.\n\n"
        f"DOCUMENTS:\n{context_block}\n\n"
        f"STUDENT QUESTION: {question}\n\n"
        f"Answer (grounded in the documents above):"
    )

    url = f"{settings.ollama_base_url.rstrip('/')}/api/generate"
    model_name = settings.ollama_model

    try:
        response = httpx.post(
            url,
            json={
                "model": model_name,
                "system": SYSTEM_PROMPT,
                "prompt": user_prompt,
                "stream": False,
                "options": {
                    "temperature": 0.3,
                    "num_predict": 1024,
                },
            },
            timeout=30.0,
        )
        if response.status_code != 200:
            raise RuntimeError(f"Ollama returned HTTP {response.status_code}: {response.text[:200]}")
        data = response.json()
        answer_text = data.get("response", "").strip()
        if not answer_text:
            answer_text = "I was unable to generate an answer. Please try rephrasing your question."

        logger.info("ollama_answer_generated", extra={"model": model_name, "question_length": len(question), "answer_length": len(answer_text)})
        return GeneratedAnswer(answer=answer_text, model=f"ollama/{model_name}", grounded=True)
    except Exception as exc:
        raise RuntimeError(f"Ollama answer generation failed on model '{model_name}': {exc}") from exc


def generate_answer(
    question: str,
    retrieved_chunks: list[dict[str, Any]],
    settings: Settings,
) -> GeneratedAnswer:
    """Generate a grounded answer using the configured AI provider and retrieved document chunks.

    Returns a GeneratedAnswer with the response text and metadata.
    Raises RuntimeError if the configured provider fails or is unconfigured.
    """
    if not retrieved_chunks:
        return GeneratedAnswer(
            answer="I couldn't find any relevant documents in the MITS knowledge base to answer your question. Please try rephrasing, or contact the relevant MITS department directly.",
            model="none",
            grounded=False,
        )

    context_block = _build_context_block(retrieved_chunks)
    provider = settings.ai_provider.lower().strip()

    if provider == "auto":
        has_gemini = bool(settings.gemini_api_key and settings.gemini_api_key.get_secret_value())
        if has_gemini:
            provider = "gemini"
        else:
            # Check if local Ollama is available
            try:
                import httpx
                r = httpx.get(f"{settings.ollama_base_url}/api/tags", timeout=1.0)
                if r.status_code == 200:
                    provider = "ollama"
                else:
                    provider = "gemini"
            except Exception:
                provider = "gemini"

    if provider == "gemini":
        return _generate_with_gemini(question, context_block, settings)
    elif provider == "ollama":
        return _generate_with_ollama(question, context_block, settings)
    else:
        raise RuntimeError(f"Unknown AI provider '{provider}'. Must be 'gemini', 'ollama', or 'auto'.")
