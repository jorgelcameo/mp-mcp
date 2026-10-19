"""Claude-assisted semantic selection constrained to the quote corpus."""

from __future__ import annotations

import asyncio
import json
import os
import urllib.error
import urllib.request

from mp_mcp.config import Settings
from mp_mcp.quotes import QUOTES, QUOTES_BY_ID
from mp_mcp.secrets import get_anthropic_api_key

DEFAULT_MODEL = "claude-haiku-4-5-20251001"


def _message(query: str, settings: Settings) -> str:
    key = get_anthropic_api_key(settings)
    model = os.getenv("ANTHROPIC_MODEL", DEFAULT_MODEL)
    candidates = [
        {"id": quote.id, "quote": quote.text, "speaker": quote.speaker}
        for quote in QUOTES
    ]
    payload = {
        "model": model,
        "max_tokens": 120,
        "system": (
            "Match the user's short text to the single most relevant item in the supplied "
            "Max Payne quote collection. The input can be about anything; look for a clear "
            "thematic or story connection, not only exact word overlap. Select only a supplied "
            "ID. Never invent, alter, or complete a quote or speaker. If no reasonable connection "
            'exists, return {"id":null,"reason":"No close match"}. Return only JSON with keys '
            '"id" and "reason"; reason must be a brief explanation of the connection.'
        ),
        "messages": [
            {
                "role": "user",
                "content": json.dumps(
                    {"input": query, "candidates": candidates}, ensure_ascii=False
                ),
            }
        ],
    }
    request = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps(payload).encode(),
        headers={
            "content-type": "application/json",
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=18) as response:
            response_data = json.loads(response.read())
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError("Quote matching service is unavailable") from exc

    text = next(
        (
            item.get("text", "")
            for item in response_data.get("content", [])
            if item.get("type") == "text"
        ),
        "",
    )
    try:
        result = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Quote matching service returned an invalid result") from exc

    quote_id = result.get("id")
    quote = QUOTES_BY_ID.get(quote_id) if isinstance(quote_id, str) else None
    if quote is None:
        return json.dumps(
            {"quote": None, "speaker": None, "reason": "No close match in the v1 collection."}
        )

    return json.dumps(
        {
            "quote": quote.text,
            "speaker": quote.speaker,
            "source": quote.source,
            "reason": str(result.get("reason", ""))[:180],
        },
        ensure_ascii=False,
    )


async def find_best_quote(query: str) -> str:
    """Match an input of at most 20 characters against the curated collection."""
    query = query.strip()
    if not query or len(query) > 20:
        return json.dumps(
            {"quote": None, "speaker": None, "reason": "Input must be between 1 and 20 characters."}
        )
    return await asyncio.to_thread(_message, query, Settings.from_env())
