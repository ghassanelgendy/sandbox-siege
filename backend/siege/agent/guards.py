"""
Security-by-Design and Behavioral Guards for Agent Frameworks.

Imports and integrates the two separate agent architectures:
  - `GenericAIAgent` from `generic_agent.py` (aliased as `GenericInsecureGuard`)
  - `SecureByDesignAgent` from `secure_agent.py` (aliased as `SecureByDesignGuard`)
"""

from __future__ import annotations

from .base import BaseGuard
from .generic_agent import GenericAIAgent
from .secure_agent import SecureByDesignAgent

# Backward-compatible aliases for existing engine callers & tests
GenericInsecureGuard = GenericAIAgent
SecureByDesignGuard = SecureByDesignAgent

_GUARDS: dict[str, BaseGuard] = {
    "secure_ai": SecureByDesignAgent("secure_ai"),
    "acme_secure": SecureByDesignAgent("acme_secure"),
    "generic_ai": GenericAIAgent("generic_ai"),
    "insecure": GenericAIAgent("insecure"),
    "acme_insecure": GenericAIAgent("acme_insecure"),
}


def get_guard(framework_id: str) -> BaseGuard | None:
    """Retrieve the behavioral guard for a framework, or None if unguarded."""
    return _GUARDS.get(framework_id)
