"""Anthropic client helpers. The API key comes from the credentials store (Settings UI)."""

import json
import re
from typing import Any, Optional, Type, TypeVar

import anthropic
from pydantic import BaseModel
from sqlalchemy.orm import Session

from . import credentials

MODEL_EXTRACT = "claude-opus-4-8"
MODEL_MERGE = "claude-opus-4-8"
MODEL_REFINE = "claude-opus-4-8"

# Models the user may pick per pipeline stage in the UI (stored in
# profile.settings_json["models"]). Cheapest → best; anything else falls back to
# the stage default. Keep in sync with the dropdown in the frontend.
ALLOWED_MODELS = ("claude-haiku-4-5", "claude-sonnet-4-6", "claude-opus-4-8")


def model_for(settings: Optional[dict[str, Any]], stage: str, default: str) -> str:
    """Resolve the model for a stage from a profile's settings, validated against the allowlist."""
    choice = ((settings or {}).get("models") or {}).get(stage)
    return choice if choice in ALLOWED_MODELS else default


class LLMNotConfigured(Exception):
    pass


def get_client(db: Session) -> anthropic.Anthropic:
    key = credentials.get_value(db, "anthropic_api_key")
    if not key:
        raise LLMNotConfigured("Anthropic API key is not set — add it in Settings first.")
    return anthropic.Anthropic(api_key=key, timeout=600.0, max_retries=2)


T = TypeVar("T", bound=BaseModel)


def parse_call(
    client: anthropic.Anthropic,
    *,
    model: str,
    system: str,
    content: Any,
    schema: Type[T],
    thinking: bool = False,
    max_tokens: int = 16000,
    cache_system: bool = False,
) -> T:
    """One schema-validated call via prompt-guided JSON + Pydantic validation.

    Measured 2026-06: API-side structured outputs (`messages.parse`) spends ~3 minutes
    failing grammar compilation on our schemas ("Grammar compilation timed out" /
    "Schema is too complex") on every call, while prompt-guided JSON returns in
    seconds and validates cleanly — so freeform IS the primary path here. Revisit if
    grammar compilation improves; validation guarantees are identical for callers.
    """
    return _freeform_parse(
        client,
        model=model,
        system=system,
        content=content,
        schema=schema,
        thinking=thinking,
        max_tokens=max_tokens,
        cache_system=cache_system,
    )


def _strip_to_json(text: str) -> str:
    """Extract the first complete top-level JSON object, ignoring any prose the model
    appends after it.

    A naive first-`{` / last-`}` slice breaks whenever the model emits trailing text that
    contains a brace — pydantic then rejects it with "Invalid JSON: trailing characters".
    Brace-counting (string- and escape-aware) returns exactly the first object instead.
    """
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n", "", text)
        if text.endswith("```"):
            text = text[:-3]
    start = text.find("{")
    if start == -1:
        return text
    depth = 0
    in_str = False
    escaped = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return text[start:]  # unbalanced (e.g. truncated output) — let validation surface it


def _response_text(response: Any) -> str:
    return "\n".join(block.text for block in response.content if block.type == "text")


def _freeform_parse(
    client: anthropic.Anthropic,
    *,
    model: str,
    system: str,
    content: Any,
    schema: Type[T],
    thinking: bool,
    max_tokens: int,
    cache_system: bool = False,
) -> T:
    schema_json = json.dumps(schema.model_json_schema(), ensure_ascii=False)
    aug_system = (
        system
        + "\n\nReturn ONLY one JSON object that validates against this JSON Schema — "
        + "no prose, no markdown fences:\n"
        + schema_json
    )
    # cache_system: for fan-out stages (scoring N jobs with one stable system prompt),
    # a cache breakpoint makes calls 2..N read the prefix at ~0.1x input price.
    system_param: Any = (
        [{"type": "text", "text": aug_system, "cache_control": {"type": "ephemeral"}}]
        if cache_system
        else aug_system
    )
    kwargs: dict[str, Any] = {}
    if thinking:
        kwargs["thinking"] = {"type": "adaptive"}
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system_param,
        messages=[{"role": "user", "content": content}],
        **kwargs,
    )
    text = _strip_to_json(_response_text(response))
    try:
        return schema.model_validate_json(text)
    except Exception as first_err:  # noqa: BLE001 - feed validation errors back once
        repair = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system_param,
            messages=[
                {"role": "user", "content": content},
                {"role": "assistant", "content": text},
                {
                    "role": "user",
                    "content": (
                        "That JSON failed validation:\n"
                        + str(first_err)[:1500]
                        + "\nReturn the corrected JSON object only."
                    ),
                },
            ],
            **kwargs,
        )
        return schema.model_validate_json(_strip_to_json(_response_text(repair)))


def friendly_llm_error(exc: Exception) -> str:
    if isinstance(exc, LLMNotConfigured):
        return str(exc)
    if isinstance(exc, anthropic.AuthenticationError):
        return "Anthropic rejected the stored API key — re-validate it in Settings."
    if isinstance(exc, anthropic.RateLimitError):
        return "Anthropic rate limit hit — wait a minute and retry."
    if isinstance(exc, anthropic.APIConnectionError):
        return "Could not reach the Anthropic API — check your network and retry."
    if isinstance(exc, anthropic.BadRequestError):
        text = str(exc)
        if "credit balance" in text.lower():
            return (
                "Your Anthropic account has no API credits — add credits under Plans & Billing "
                "on platform.claude.com, then hit Retry."
            )
        return f"Anthropic rejected the request (400): {text[:300]}"
    if isinstance(exc, anthropic.APIStatusError):
        return f"Anthropic API error (HTTP {exc.status_code}) — retry in a moment."
    return f"{type(exc).__name__}: {exc}"


def short_error(exc: Exception, limit: int = 500) -> Optional[str]:
    text = friendly_llm_error(exc)
    return text[:limit]
