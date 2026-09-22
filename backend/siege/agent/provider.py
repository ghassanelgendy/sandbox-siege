"""
Model providers (PRD FR-4.1, FR-4.6, FR-4.7).

Both gateways are OpenAI-compatible, so the openai SDK with a base_url override
is sufficient -- LiteLLM was deliberately dropped (decision D-2).

The roster is DISCOVERED AT RUNTIME and health-checked. Never hardcode it:
provider credit state changes without warning (decision D-6).
"""

from __future__ import annotations

import json
import re
import time
from typing import Any

from openai import OpenAI

from ..config import settings

PROVIDERS = ("bynara", "dahl", "groq")

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


# A health probe only needs to see whether the model answers and can emit a
# tool_call -- not to wait out a full generation. Capping it well under the
# run-time timeout bounds how long /api/models can take on a slow straggler.
PROBE_TIMEOUT_S = 20.0

def client_for(provider: str, timeout: float | None = None) -> OpenAI:
    # Check custom provider registry first
    from .custom_providers import provider_registry
    cp = provider_registry.get_provider(provider)
    if cp:
        return OpenAI(
            base_url=cp.base_url,
            api_key=cp.api_key or "sk-dummy-key",
            timeout=timeout or settings.siege_api_timeout_s,
            max_retries=0,
        )

    base_url, api_key = settings.provider_config(provider)
    if not api_key:
        raise ProviderError(
            f"No API key configured for provider {provider!r}. Set "
            f"{provider.upper()}_API_KEY in .env",
            fatal=True,
        )
    return OpenAI(base_url=base_url, api_key=api_key,
                  timeout=timeout or settings.siege_api_timeout_s, max_retries=0)


def chat(provider: str, model: str, messages: list[dict[str, Any]],
         tools: list[dict[str, Any]] | None = None, max_retries: int = 2,
         timeout: float | None = None) -> Any:
    """One chat completion, with bounded retries on transient failures (FR-4.6)."""
    client = client_for(provider, timeout=timeout)
    kwargs: dict[str, Any] = {"model": model, "messages": messages}
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"

    last = ""
    effective_retries = 5 if provider == "groq" else max_retries
    for attempt in range(effective_retries + 1):
        try:
            return client.chat.completions.create(**kwargs)
        except Exception as exc:  # noqa: BLE001
            last = str(exc)
            if _is_fatal(last):
                raise ProviderError(f"{provider}/{model}: {last}", fatal=True) from exc
            if attempt < effective_retries:
                # If provider returned a rate limit cooldown message (e.g. 'try again in 3.5s' or '800ms')
                # extract and sleep the exact requested time + jitter
                sleep_s = float(2 ** attempt)
                rate_match = re.search(r"try again in ([\d\.]+)(s|ms)", last)
                if rate_match:
                    val = float(rate_match.group(1))
                    unit = rate_match.group(2)
                    cooldown = val if unit == "s" else (val / 1000.0)
                    sleep_s = max(sleep_s, cooldown + 0.5)
                time.sleep(sleep_s)
    raise ProviderError(f"{provider}/{model} failed after {effective_retries + 1} attempts: {last}")


def get_fallback_candidates(provider: str, model: str) -> list[tuple[str, str]]:
    """Determine prioritized list of (provider, model) fallback pairs for resilient execution."""
    candidates: list[tuple[str, str]] = [(provider, model)]

    # Same-provider alternatives
    if provider == "groq":
        groq_alts = ["openai/gpt-oss-120b", "openai/gpt-oss-20b", "qwen/qwen3.8-27b", "qwen/qwen3.6-27b"]
        for m in groq_alts:
            if m != model and (provider, m) not in candidates:
                candidates.append((provider, m))
        # Cross-provider fallbacks if Groq limits are exhausted
        if settings.dahl_api_key:
            candidates.append(("dahl", "deepseek-ai/DeepSeek-V4-Flash-0731"))
            candidates.append(("dahl", "MiniMaxAI/MiniMax-M2.7"))
        if settings.bynara_api_key:
            candidates.append(("bynara", "deepseek-v4-pro-free"))
    elif provider == "dahl":
        dahl_alts = ["deepseek-ai/DeepSeek-V4-Flash-0731", "MiniMaxAI/MiniMax-M2.7"]
        for m in dahl_alts:
            if m != model and (provider, m) not in candidates:
                candidates.append((provider, m))
        if settings.groq_api_key:
            candidates.append(("groq", "openai/gpt-oss-120b"))
            candidates.append(("groq", "openai/gpt-oss-20b"))
    elif provider == "bynara":
        bynara_alts = ["deepseek-v4-pro-free", "mistral-large"]
        for m in bynara_alts:
            if m != model and (provider, m) not in candidates:
                candidates.append((provider, m))
        if settings.groq_api_key:
            candidates.append(("groq", "openai/gpt-oss-120b"))
            candidates.append(("groq", "openai/gpt-oss-20b"))
        if settings.dahl_api_key:
            candidates.append(("dahl", "deepseek-ai/DeepSeek-V4-Flash-0731"))
    else:
        # Custom provider or unrecognized: fallback to groq / dahl if available
        if settings.groq_api_key:
            candidates.append(("groq", "openai/gpt-oss-120b"))
        if settings.dahl_api_key:
            candidates.append(("dahl", "deepseek-ai/DeepSeek-V4-Flash-0731"))

    return candidates


def chat_with_fallback(
    provider: str,
    model: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
    timeout: float | None = None,
    on_fallback: Any = None,
    _chat_fn: Any = None,
) -> tuple[Any, str, str]:
    """Execute chat completion with cascading fallback across candidate models/providers.

    Returns tuple of (response, active_provider, active_model).
    Invokes on_fallback(failed_provider, failed_model, next_provider, next_model, reason)
    when a fallback occurs.
    """
    candidates = get_fallback_candidates(provider, model)
    errors: list[str] = []

    effective_chat = _chat_fn or chat
    for idx, (cand_provider, cand_model) in enumerate(candidates):
        try:
            resp = effective_chat(
                provider=cand_provider,
                model=cand_model,
                messages=messages,
                tools=tools,
                timeout=timeout,
            )
            return resp, cand_provider, cand_model
        except Exception as exc:
            err_msg = str(exc)
            errors.append(f"{cand_provider}/{cand_model}: {err_msg}")
            if idx + 1 < len(candidates):
                next_p, next_m = candidates[idx + 1]
                if callable(on_fallback):
                    try:
                        on_fallback(cand_provider, cand_model, next_p, next_m, err_msg)
                    except Exception:
                        pass
                continue
            # If all candidates exhausted, raise combined error
            break

    raise ProviderError("All cascading model fallbacks failed:\n" + "\n".join(errors))


def discover_models(provider: str) -> list[str]:
    """Ask the provider what it serves (FR-4.7)."""
    from .custom_providers import provider_registry
    cp = provider_registry.get_provider(provider)
    if cp and cp.models:
        return sorted(cp.models)

    try:
        models = [m.id for m in client_for(provider, timeout=10.0).models.list().data]
        if provider == "groq":
            # Filter out speech/audio models (whisper, orpheus) and models with known tool incompatibilities
            supported = {
                "openai/gpt-oss-20b",
                "openai/gpt-oss-120b",
                "openai/gpt-oss-safeguard-20b",
                "qwen/qwen3.6-27b",
                "qwen/qwen3.8-27b",
            }
            return sorted([m for m in models if m in supported])
        return sorted(models)
    except Exception:
        return []


def health_check_model(provider: str, model: str) -> dict[str, Any]:
    """Probe a model with a minimal tool-calling request.

    Returns {healthy, supports_tools, error}. A model that answers but cannot
    emit tool_calls is still usable via the text-protocol fallback (FR-4.3).
    """
    if provider == "insecure":
        return {"healthy": True, "supports_tools": True, "error": None}
    try:
        resp = chat(provider, model,
                    [{"role": "user", "content": "List the S3 buckets. Use the tool."}],
                    tools=_PROBE_TOOL, max_retries=0, timeout=PROBE_TIMEOUT_S)
    except Exception as exc:  # noqa: BLE001
        return {"healthy": False, "supports_tools": False, "error": str(exc)[:200]}

    try:
        msg = resp.choices[0].message
        return {"healthy": True, "supports_tools": bool(getattr(msg, "tool_calls", None)),
                "error": None}
    except Exception as exc:  # noqa: BLE001
        return {"healthy": False, "supports_tools": False, "error": str(exc)[:200]}
