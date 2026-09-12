"""
Custom LLM Provider Storage and Registry.

Allows users to dynamically register arbitrary OpenAI-compatible LLM endpoints
(e.g., local Ollama, vLLM, OpenAI, OpenRouter, Anthropic proxies, Together AI, Mistral)
with custom base_url, api_key, and model lists.
Persisted to `~/.siege/custom_providers.json`.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger("siege.providers")

CACHE_DIR = Path(os.environ.get("SIEGE_HOME", Path.home() / ".siege"))
PROVIDERS_FILE = CACHE_DIR / "custom_providers.json"


@dataclass
class CustomProvider:
    id: str  # e.g. "ollama", "openrouter", "my-vllm"
    name: str  # e.g. "Local Ollama"
    base_url: str  # e.g. "http://localhost:11434/v1"
    api_key: str = ""  # optional for local models
    models: list[str] | None = None  # explicit models or empty to discover via /models


class ProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, CustomProvider] = {}
        self._load()

    def _load(self) -> None:
        if PROVIDERS_FILE.is_file():
            try:
                data = json.loads(PROVIDERS_FILE.read_text(encoding="utf-8"))
                for item in data:
                    cp = CustomProvider(**item)
                    self._providers[cp.id.lower()] = cp
            except Exception as exc:
                logger.warning("Failed to load custom_providers.json: %s", exc)

    def _save(self) -> None:
        try:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            out = [asdict(p) for p in self._providers.values()]
            PROVIDERS_FILE.write_text(json.dumps(out, indent=2), encoding="utf-8")
        except Exception as exc:
            logger.warning("Failed to save custom_providers.json: %s", exc)

    def list_providers(self) -> list[CustomProvider]:
        return list(self._providers.values())

    def get_provider(self, provider_id: str) -> CustomProvider | None:
        return self._providers.get(provider_id.lower())

    def add_provider(self, provider: CustomProvider) -> CustomProvider:
        pid = provider.id.lower().strip()
        provider.id = pid
        self._providers[pid] = provider
        self._save()
        return provider

    def delete_provider(self, provider_id: str) -> bool:
        pid = provider_id.lower().strip()
        if pid in self._providers:
            del self._providers[pid]
            self._save()
            return True
        return False


provider_registry = ProviderRegistry()
