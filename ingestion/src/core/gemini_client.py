"""
Gemini API client singleton.
Provides a `generate_structured` helper that enforces a Pydantic schema
on the model's JSON output, retrying on malformed responses.
"""

from __future__ import annotations

import json
from typing import Type, TypeVar

from google import genai
from google.genai import types
from pydantic import BaseModel, ValidationError

from src.core.config import GEMINI_API_KEY, GEMINI_MODEL
from src.core.logger import logger

T = TypeVar("T", bound=BaseModel)

# Module-level singleton
_client: genai.Client | None = None


def get_client() -> genai.Client:
    global _client
    if _client is None:
        if not GEMINI_API_KEY:
            raise EnvironmentError("GEMINI_API_KEY is not set in .env")
        _client = genai.Client(api_key=GEMINI_API_KEY)
        logger.info(f"Gemini client initialized (model: {GEMINI_MODEL})")
    return _client


def generate_structured(
    prompt: str,
    schema: Type[T],
    max_retries: int = 3,
) -> T:
    """
    Send `prompt` to Gemini and parse the response into `schema`.
    Retries up to `max_retries` times on validation failures.
    """
    client = get_client()

    for attempt in range(1, max_retries + 1):
        try:
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=schema,
                ),
            )
            raw = response.text
            parsed = schema.model_validate_json(raw)
            return parsed
        except ValidationError as e:
            logger.warning(f"[Attempt {attempt}/{max_retries}] Validation error: {e}")
        except Exception as e:
            logger.error(f"[Attempt {attempt}/{max_retries}] Gemini API error: {e}")
            raise

    raise RuntimeError(f"Failed to get valid response after {max_retries} attempts.")
