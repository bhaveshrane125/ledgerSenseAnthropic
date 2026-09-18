"""Server-only settings and demo matching-policy defaults.

Values here are proposed defaults for the POC and must be validated against
real client samples before this is used beyond a local demo.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _load_env_once() -> None:
    """Explicitly load `.env` from the project root, if present."""
    env_path = _PROJECT_ROOT / ".env"
    if env_path.exists():
        load_dotenv(env_path)


@dataclass(frozen=True)
class UploadLimits:
    max_file_bytes: int = 10 * 1024 * 1024
    max_pages: int = 10
    max_total_bytes: int = 3 * 10 * 1024 * 1024


DEFAULT_CURRENCY_MINOR_UNITS: dict[str, int] = {
    "INR": 2,
    "USD": 2,
    "EUR": 2,
    "GBP": 2,
    "JPY": 0,
}

DEFAULT_UNIT_ALIASES: dict[str, str] = {
    "ea": "ea",
    "each": "ea",
    "pc": "ea",
    "pcs": "ea",
    "piece": "ea",
    "pieces": "ea",
    "nos": "ea",
    "no": "ea",
    "unit": "ea",
    "units": "ea",
    "ltr": "ltr",
    "litre": "ltr",
    "liter": "ltr",
    "litres": "ltr",
    "liters": "ltr",
    "l": "ltr",
    "mtr": "mtr",
    "meter": "mtr",
    "metre": "mtr",
    "meters": "mtr",
    "metres": "mtr",
    "m": "mtr",
    "kg": "kg",
    "kgs": "kg",
    "kilogram": "kg",
    "kilograms": "kg",
    "pair": "pair",
    "pairs": "pair",
    "roll": "roll",
    "rolls": "roll",
    "box": "box",
    "boxes": "box",
}


@dataclass(frozen=True)
class MatchingPolicy:
    """Max rounding difference allowed per amount check, in currency minor units,
    plus the currency/unit lookup tables used while normalizing extracted data."""

    rounding_tolerance_minor_units: int = 1
    currency_minor_units: dict[str, int] = field(default_factory=lambda: dict(DEFAULT_CURRENCY_MINOR_UNITS))
    unit_aliases: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_UNIT_ALIASES))


DEFAULT_UPLOAD_LIMITS = UploadLimits()
DEFAULT_MATCHING_POLICY = MatchingPolicy()


@dataclass(frozen=True)
class AppConfig:
    # Claude is reached via the company's Azure AI Foundry deployment, not the
    # direct Anthropic API — see extraction.py / content_matching.py, which
    # construct `anthropic.AnthropicFoundry(api_key=..., base_url=...)`.
    anthropic_foundry_api_key: str
    anthropic_foundry_base_url: str
    anthropic_deployment_name: str
    # Overall wall-clock budget for one extraction call, in seconds.
    extraction_timeout_seconds: float
    # Bounded application-level retries on transient provider failures (SDK retries disabled).
    extraction_max_attempts: int
    upload: UploadLimits
    policy: MatchingPolicy


_cached: AppConfig | None = None


def get_config() -> AppConfig:
    global _cached
    if _cached is not None:
        return _cached

    _load_env_once()

    api_key = os.environ.get("ANTHROPIC_FOUNDRY_API_KEY")
    if not api_key:
        raise RuntimeError("Missing required environment variable: ANTHROPIC_FOUNDRY_API_KEY")

    base_url = os.environ.get("ANTHROPIC_FOUNDRY_BASE_URL")
    if not base_url:
        raise RuntimeError("Missing required environment variable: ANTHROPIC_FOUNDRY_BASE_URL")

    _cached = AppConfig(
        anthropic_foundry_api_key=api_key,
        anthropic_foundry_base_url=base_url,
        anthropic_deployment_name=os.environ.get("ANTHROPIC_DEPLOYMENT_NAME") or "claude-sonnet-5",
        extraction_timeout_seconds=45.0,
        extraction_max_attempts=2,
        upload=DEFAULT_UPLOAD_LIMITS,
        policy=DEFAULT_MATCHING_POLICY,
    )
    return _cached


def reset_config_cache() -> None:
    """Test-only escape hatch to force settings to be re-read."""
    global _cached
    _cached = None
