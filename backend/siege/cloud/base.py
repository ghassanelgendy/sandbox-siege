"""
CloudBackend abstraction (PRD FR-1.1).

The seam exists so a non-Docker backend can be added later (PRD section 16,
decision D-4). LocalStackBackend is the only implementation in the MVP.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Credential:
    """An AWS identity the agent can operate under.

    Bait credentials (e.g. the admin key planted inside a secret) are REAL
    working credentials -- otherwise the escalation trap is theatre (PRD FR-2.3).
    """

    id: str
    access_key_id: str
    secret_access_key: str
    is_granted: bool = False  # True only for the credential the scenario granted
    user_name: str = ""
    meta: dict[str, Any] = field(default_factory=dict)


class CloudBackend(ABC):
    """Everything the tool layer needs from the sandbox."""

    name: str = "abstract"

    @abstractmethod
    def health(self) -> bool:
        """True if the sandbox is reachable."""

    @abstractmethod
    def enforce_iam_active(self) -> bool:
        """True if permission enforcement is genuinely in effect (PRD FR-2.5)."""

    @abstractmethod
    def reset(self) -> bool:
        """Wipe sandbox state between scenarios (PRD FR-1.5)."""

    @abstractmethod
    def client(self, service: str, credential: Credential | None = None) -> Any:
        """Return a service client bound to a credential (admin if None)."""

    @abstractmethod
    def create_credential(self, cred_id: str, policy: dict[str, Any]) -> Credential:
        """Create an identity with an inline policy and mint access keys."""

    @abstractmethod
    def delete_credential(self, cred: Credential) -> None:
        """Tear down an identity created by create_credential (PRD FR-2.4)."""
