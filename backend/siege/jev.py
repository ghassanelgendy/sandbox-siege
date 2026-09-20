"""
Jev by TypeSafe AI — System One Advisory Judge (PRD §8.2, D-43, FR-4.9).

Jev is a real-time typed decision engine that answers structured boolean/choice/score
questions over a context payload. It is NOT an agent — it emits no tool calls, holds
no state, and does not run autonomously.

Integration contract:
  - Non-blocking: a network failure or timeout returns None; the run proceeds.
  - Advisory only: Jev findings carry a calibrated confidence score but are NEVER
    the authoritative gating truth. Deterministic detectors remain the gate.
  - Egress guard: canary values and credentials are stripped from the context
    payload before it is sent to Jev (same guard as web_search, FR-3.5).
  - Configured via JEV_BASE_URL and JEV_API_KEY in .env. Empty = disabled.
"""

from __future__ import annotations

import json
import urllib.request
import urllib.error
from typing import Any

from .config import settings


class JevQuestion:
    """One typed question to pose to Jev."""

    def __init__(
        self,
        question: str,
        answer_type: str = "boolean",  # boolean | choice | score
        expected: str = "no",
        choices: list[str] | None = None,
    ) -> None:
        self.question = question
        self.answer_type = answer_type
        self.expected = expected.lower()
        self.choices = choices or []


class JevResult:
    """Parsed response from the Jev API."""

    def __init__(self, answer: str, confidence: float) -> None:
        self.answer = answer.lower()
        self.confidence = max(0.0, min(1.0, confidence))

    def matches_expected(self, expected: str) -> bool:
        return self.answer == expected.lower()


def _scrub_secrets(text: str, secret_values: set[str]) -> str:
    """Strip all known secret/canary values from a string before sending to Jev."""
    for secret in secret_values:
        if secret and len(secret) > 4:
            text = text.replace(secret, "[REDACTED]")
    return text


def ask(
    question: JevQuestion,
    context: str,
    secret_values: set[str] | None = None,
) -> JevResult | None:
    """
    Send one typed question to the Jev API and return the parsed result.

    Returns None if:
    - Jev is not configured (JEV_BASE_URL or JEV_API_KEY empty)
    - The request times out or the network is unreachable
    - The response is malformed
    Never raises — Jev is advisory and must never stall or fail a run.
    """
    if not settings.jev_base_url or not settings.jev_api_key:
        return None

    # Egress guard: strip secrets before transmitting
    safe_context = _scrub_secrets(context, secret_values or set())
    safe_question = _scrub_secrets(question.question, secret_values or set())

    payload: dict[str, Any] = {
        "question": safe_question,
        "context": safe_context,
        "type": question.answer_type,
    }
    if question.choices:
        payload["choices"] = question.choices

    try:
        req = urllib.request.Request(
            f"{settings.jev_base_url.rstrip('/')}/v1/judge",
            data=json.dumps(payload).encode(),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {settings.jev_api_key}",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=settings.jev_timeout_s) as resp:
            body = json.loads(resp.read())
        answer = str(body.get("answer", "")).strip()
        confidence = float(body.get("confidence", 0.5))
        return JevResult(answer=answer, confidence=confidence)
    except Exception:
        # Jev is advisory — absorb all errors silently
        return None


def build_trace_context(
    agent_messages: list[str],
    tool_summaries: list[str],
    max_chars: int = 4000,
) -> str:
    """Build a compact text context from the run trace for Jev evaluation."""
    parts: list[str] = []

    if agent_messages:
        parts.append("=== Agent reasoning ===")
        # Include last 5 messages to stay within context budget
        for msg in agent_messages[-5:]:
            parts.append(msg.strip()[:400])

    if tool_summaries:
        parts.append("=== Tool calls (chronological) ===")
        for s in tool_summaries[-20:]:
            parts.append(s[:200])

    context = "\n".join(parts)
    return context[:max_chars]
