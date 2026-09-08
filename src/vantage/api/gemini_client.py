"""Async client for Google Gemini via the REST generateContent endpoint."""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any

import httpx
from pydantic import BaseModel

from vantage.config.settings import get_settings
from vantage.core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()


class GeminiError(Exception):
    pass


class GeminiResponse(BaseModel):
    text: str
    raw_data: dict


class GeminiClient:
    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
    ):
        self.api_key = api_key or settings.gemini_api_key
        self.base_url = base_url or settings.gemini_base_url
        self.model = model or settings.gemini_model
        self._client: httpx.AsyncClient | None = None
        self._semaphore: asyncio.Semaphore | None = None

    async def __aenter__(self) -> GeminiClient:
        limits = httpx.Limits(max_connections=10, max_keepalive_connections=5)
        timeout = httpx.Timeout(120.0, connect=10.0)
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            limits=limits,
            timeout=timeout,
        )
        self._semaphore = asyncio.Semaphore(5)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    def _get_client(self) -> httpx.AsyncClient:
        if not self._client:
            raise RuntimeError("Client not initialized. Use async context manager.")
        return self._client

    async def complete(
        self,
        system_prompt: str = "",
        user_prompt: str = "",
        temperature: float | None = None,
        max_tokens: int | None = None,
        mime_type: str | None = None,
    ) -> str:
        """Run a single-turn generation and return the text reply."""
        if not self.api_key:
            raise GeminiError(
                "GEMINI_API_KEY is not configured. Add it to your .env file."
            )
        parts: list[dict[str, Any]] = [{"text": user_prompt}]
        contents: list[dict[str, Any]] = [{"role": "user", "parts": parts}]
        body: dict[str, Any] = {"contents": contents}
        if system_prompt:
            body["systemInstruction"] = {"parts": [{"text": system_prompt}]}
        generation: dict[str, Any] = {}
        if temperature is not None:
            generation["temperature"] = temperature
        if max_tokens is not None:
            generation["maxOutputTokens"] = max_tokens
        if mime_type is not None:
            generation["responseMimeType"] = mime_type
        if generation:
            body["generationConfig"] = generation

        client = self._get_client()
        async with self._semaphore:
            data = await self._post_with_retry(client, body)

        try:
            text = data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError, TypeError):
            reason = (
                data.get("promptFeedback", {})
                .get("blockReason", "empty candidate")
                if isinstance(data, dict)
                else "non-dict response"
            )
            raise GeminiError(
                f"Gemini returned no text (blockReason={reason})"
            ) from None
        return text.strip()

    async def _post_with_retry(
        self, client: httpx.AsyncClient, body: dict[str, Any]
    ) -> dict:
        """POST generateContent with retry/backoff on transient 429/5xx errors."""
        max_retries = 6
        for attempt in range(max_retries):
            try:
                resp = await client.post(
                    f"/models/{self.model}:generateContent",
                    headers={"x-goog-api-key": self.api_key},
                    json=body,
                )
                if resp.status_code == 404 and "no longer available" in resp.text:
                    raise GeminiError(
                        f"Model {self.model} not available. Update GEMINI_MODEL: "
                        f"{resp.text[:300]}"
                    )
                resp.raise_for_status()
                return resp.json()
            except httpx.HTTPStatusError as e:
                status = e.response.status_code
                if status in (429, 500, 502, 503, 504) and attempt < max_retries - 1:
                    wait = 2 ** attempt
                    if status == 429:
                        wait = max(wait, _retry_seconds(e.response.text))
                        logger.warning(
                            "Gemini rate limited, waiting",
                            status=status,
                            wait_s=wait,
                            attempt=attempt,
                        )
                    else:
                        logger.warning(
                            "Gemini transient error, retrying",
                            status=status,
                            attempt=attempt,
                            wait_s=wait,
                        )
                    await asyncio.sleep(wait)
                    continue
                logger.error(
                    "Gemini API error",
                    status=status,
                    error=str(e),
                    body=e.response.text[:500],
                )
                raise GeminiError(f"Gemini request failed ({status})") from e
            except httpx.RequestError as e:
                logger.error("Gemini request failed", error=str(e))
                raise GeminiError(f"Gemini request failed: {e}") from e

    async def complete_json(
        self,
        system_prompt: str = "",
        user_prompt: str = "",
        temperature: float | None = None,
        max_tokens: int | None = None,
        schema: dict[str, Any] | None = None,
    ) -> dict:
        """Request a JSON object response and parse it defensively."""
        text = await self.complete(
            system_prompt,
            user_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            mime_type="application/json",
        )
        return _extract_json(text)


def _extract_json(text: str) -> dict:
    """Extract the JSON object from a model reply, tolerating code fences."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```", 2)[1]
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
        cleaned = cleaned.strip()

    json_start_markers = ["{", "["]
    start = -1
    for marker in json_start_markers:
        idx = cleaned.find(marker)
        if idx != -1 and (start == -1 or idx < start):
            start = idx
    end = cleaned.rfind("}") if cleaned.rfind("}") != -1 else cleaned.rfind("]")
    if start == -1 or end == -1 or end < start:
        raise GeminiError(f"Model reply contained no JSON object: {text[:300]}")
    try:
        parsed = json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError:
        # Nested double-encoded strings (e.g. model may return strings with
        # embedded newlines) can break strict parsing. Fall back to a lenient
        # decoder that unescapes common artifacts.
        parsed = json.loads(cleaned[start : end + 1].replace("\n", "\\n"))
    if not isinstance(parsed, dict):
        raise GeminiError("Model reply JSON was not an object")
    return parsed


def _retry_seconds(body: str) -> float:
    """Extract a suggested retry delay (seconds) from a Gemini 429 error body."""
    low = body.lower()
    match = re.search(r"retry in ([\d.]+)s", low)
    if match:
        return min(float(match.group(1)), 60.0)
    match = re.search(r"retry_delay.*?seconds[^0-9]*([\d.]+)", low)
    if match:
        return min(float(match.group(1)), 60.0)
    return 8.0