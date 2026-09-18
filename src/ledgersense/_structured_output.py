"""Shared plumbing for Anthropic structured-output (JSON-schema) calls.

Used by both `extraction.py` (per-document extraction) and
`content_matching.py` (cross-document linkage/party/item-mapping judgments)
so the retry loop, transient-error classification, and the UNKNOWN/0/""
sentinel encoding live in exactly one place.

Why the sentinel encoding: the Messages API caps a JSON Schema at 16
union-typed ("anyOf"/type-array) properties before compilation cost blows up,
and these document/judgment schemas need more nullable fields than that.
Instead of `anyOf: [{type}, {type: "null"}]`, every "missing" value is
encoded with a plain-typed sentinel — the literal string "UNKNOWN", or 0/""
for page/snippet-shaped fields — and `desentinel()` converts those back to
`None` right after JSON parsing, before pydantic validation ever sees them.
"""

from __future__ import annotations

import json
import time
from typing import Any

import anthropic

UNKNOWN = "UNKNOWN"


class StructuredOutputError(Exception):
    def __init__(self, message: str, retryable: bool) -> None:
        super().__init__(message)
        self.retryable = retryable


def sentinel_string(hint: str) -> dict[str, Any]:
    return {
        "type": "string",
        "description": f'{hint} Use the exact literal "{UNKNOWN}" if this cannot be determined.',
    }


SENTINEL_DECIMAL = sentinel_string(
    'Plain decimal, e.g. "1234.56" (no currency symbols or thousands separators).'
)


def desentinel(value: Any, key_hint: str | None = None) -> Any:
    """Reverses the UNKNOWN/0/"" sentinel encoding back to None before validation."""
    if isinstance(value, str):
        if value == UNKNOWN:
            return None
        if key_hint == "snippet" and value == "":
            return None
        return value
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        if key_hint == "page" and value == 0:
            return None
        return value
    if isinstance(value, list):
        return [desentinel(v) for v in value]
    if isinstance(value, dict):
        return {k: desentinel(v, k) for k, v in value.items()}
    return value


def is_retryable(err: BaseException) -> bool:
    if isinstance(err, anthropic.APIStatusError):
        status = err.status_code
        return status in (429, 408, 409) or status >= 500
    return isinstance(err, (anthropic.APIConnectionError, anthropic.APITimeoutError))


def call_structured(
    client: anthropic.Anthropic,
    *,
    model: str,
    system: str,
    content: list[dict[str, Any]],
    json_schema: dict[str, Any],
    max_attempts: int,
    timeout_seconds: float,
    error_context: str,
    max_tokens: int = 8000,
) -> Any:
    """Runs one structured-output Messages call with bounded retries.

    Returns the desentineled (sentinel -> None) parsed JSON body; callers
    validate it against their own pydantic model. Raises
    `StructuredOutputError` (with `.retryable`) on any failure — SDK retries
    are disabled by the caller-constructed client (`max_retries=0`), so this
    loop is the only retry logic in play, never both.
    """
    last_error: BaseException | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            # The SDK's message/content param TypedDicts don't unify well with a
            # dynamically-built dict[str, Any] payload; the runtime shape is correct
            # (validated against the live API during manual verification).
            response = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": content}],
                output_config={"format": {"type": "json_schema", "schema": json_schema}},
                timeout=timeout_seconds,
            )  # type: ignore[call-overload]
        except Exception as err:  # re-raised as StructuredOutputError below
            last_error = err
            retryable = is_retryable(err)
            if not retryable or attempt == max_attempts:
                raise StructuredOutputError(f"{error_context}: call failed ({err}).", retryable) from err
            time.sleep(0.3 * attempt)
            continue

        text_block = next((b for b in response.content if b.type == "text"), None)
        if text_block is None:
            raise StructuredOutputError(f"{error_context}: model returned no text output.", False)

        try:
            parsed_json = json.loads(text_block.text)
        except json.JSONDecodeError as err:
            raise StructuredOutputError(f"{error_context}: model output was not valid JSON.", False) from err

        return desentinel(parsed_json)

    # Unreachable in practice (the loop always returns or raises), but keeps type-checkers happy.
    raise StructuredOutputError(
        f"{error_context}: call failed after {max_attempts} attempts ({last_error}).", True
    )
