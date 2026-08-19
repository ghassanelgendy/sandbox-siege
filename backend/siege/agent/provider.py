"""
Model providers (PRD FR-4.1, FR-4.6, FR-4.7).

Both gateways are OpenAI-compatible, so the openai SDK with a base_url override
is sufficient -- LiteLLM was deliberately dropped (decision D-2).

The roster is DISCOVERED AT RUNTIME and health-checked. Never hardcode it:
provider credit state changes without warning (decision D-6).
"""

from __future__ import annotations

import time
from typing import Any

from openai import OpenAI

from ..config import settings

PROVIDERS = ("bynara", "dahl")

# Errors that must NOT be retried -- retrying a billing failure just wastes time.
FATAL_MARKERS = ("payment_required", "insufficient credits", "invalid_api_key",
                 "authentication", "quota")

_PROBE_TOOL = [{
    "type": "function",
    "function": {
        "name": "s3_list_buckets",
        "description": "List all S3 buckets",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
}]


class ProviderError(RuntimeError):
    def __init__(self, message: str, fatal: bool = False) -> None:
        super().__init__(message)
        self.fatal = fatal


def _is_fatal(message: str) -> bool:
    low = message.lower()
    return any(m in low for m in FATAL_MARKERS)


def client_for(provider: str) -> OpenAI:
    base_url, api_key = settings.provider_config(provider)
    if not api_key:
        raise ProviderError(
            f"No API key configured for provider {provider!r}. Set "
            f"{provider.upper()}_API_KEY in .env",
            fatal=True,
        )
    return OpenAI(base_url=base_url, api_key=api_key, timeout=settings.siege_api_timeout_s)


def chat(provider: str, model: str, messages: list[dict[str, Any]],
         tools: list[dict[str, Any]] | None = None, max_retries: int = 2) -> Any:
    """One chat completion, with bounded retries on transient failures (FR-4.6)."""
    client = client_for(provider)
    kwargs: dict[str, Any] = {"model": model, "messages": messages}
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"

    last = ""
    for attempt in range(max_retries + 1):
        try:
            return client.chat.completions.create(**kwargs)
        except Exception as exc:  # noqa: BLE001
            last = str(exc)
            if _is_fatal(last):
                raise ProviderError(f"{provider}/{model}: {last}", fatal=True) from exc
            if attempt < max_retries:
                time.sleep(2 ** attempt)
    raise ProviderError(f"{provider}/{model} failed after {max_retries + 1} attempts: {last}")


def discover_models(provider: str) -> list[str]:
    """Ask the provider what it serves (FR-4.7)."""
    try:
        return sorted(m.id for m in client_for(provider).models.list().data)
    except Exception:
        return []


def health_check_model(provider: str, model: str) -> dict[str, Any]:
    """Probe a model with a minimal tool-calling request.

    Returns {healthy, supports_tools, error}. A model that answers but cannot
    emit tool_calls is still usable via the text-protocol fallback (FR-4.3).
    """
    try:
        resp = chat(provider, model,
                    [{"role": "user", "content": "List the S3 buckets. Use the tool."}],
                    tools=_PROBE_TOOL, max_retries=0)
    except Exception as exc:  # noqa: BLE001
        return {"healthy": False, "supports_tools": False, "error": str(exc)[:200]}

    try:
        msg = resp.choices[0].message
        return {"healthy": True, "supports_tools": bool(getattr(msg, "tool_calls", None)),
                "error": None}
    except Exception as exc:  # noqa: BLE001
        return {"healthy": False, "supports_tools": False, "error": str(exc)[:200]}
