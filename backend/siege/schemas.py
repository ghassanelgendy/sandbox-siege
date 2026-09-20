"""
FROZEN CONTRACT — see docs/PRD.md section 9.

Every field here is mirrored in frontend/src/types.ts. Changing anything in this
file requires updating, in the same commit:
  1. frontend/src/types.ts
  2. backend/fixtures/report_sample.json
  3. docs/PRD.md  section 9
  4. docs/FLOW.md payload examples
See AGENTS.md section 0.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field

Severity = Literal["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"]
Outcome = Literal["pass", "partial", "fail"]
Decision = Literal["ALLOW", "WARN", "DENY"]
Grade = Literal["A", "B", "C", "D", "F"]
Gate = Literal["PASS", "FAIL"]
Mode = Literal["live", "replay"]


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------- #
# Events
# --------------------------------------------------------------------------- #

class EventType:
    """String constants for Event.type. See docs/PRD.md section 9."""

    RUN_STARTED = "run.started"
    SCENARIO_STARTED = "scenario.started"
    AGENT_MESSAGE = "agent.message"
    TOOL_CALLED = "tool.called"
    IAM_VERDICT = "iam.verdict"
    POLICY_VERDICT = "policy.verdict"
    TOOL_RESULT = "tool.result"
    TRAP_TRIGGERED = "trap.triggered"
    SCENARIO_FINISHED = "scenario.finished"
    RUN_FINISHED = "run.finished"
    RUN_ERROR = "run.error"


class Event(BaseModel):
    seq: int
    ts: datetime = Field(default_factory=utcnow)
    run_id: str
    scenario_id: str | None = None
    type: str
    data: dict[str, Any] = Field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Findings & Attribution (D-41, PRD §8.1, FR-D.5)
# --------------------------------------------------------------------------- #

class ChatLine(BaseModel):
    role: Literal["agent", "user", "system"] = "agent"
    content: str
    step: int = 0


class AttributedCall(BaseModel):
    step: int
    tool: str
    args: dict[str, Any] = Field(default_factory=dict)
    iam_decision: Literal["ALLOW", "DENY", "N/A"] = "N/A"
    resource: str = ""


class SeedItemRef(BaseModel):
    kind: str  # bucket | db | ec2 | secret | parameter | table | log_group | other
    name: str
    terraform_source: str | None = None


class Finding(BaseModel):
    """A single detected behaviour. INFO severity denotes a *positive* finding."""

    trap_id: str
    severity: Severity
    title: str
    evidence: str  # must cite the concrete call + step index (PRD FR-D.1)
    explanation: str
    remediation: str
    step: int = 0
    cve_id: str | None = None
    cvss_score: float | None = None
    cwe_id: str | None = None
    atlas_id: str | None = None
    confidence: float | None = None  # optional Jev/detector calibrated confidence (D-43)
    chat: list[ChatLine] = Field(default_factory=list)
    tool_calls: list[AttributedCall] = Field(default_factory=list)
    seed_items: list[SeedItemRef] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Results
# --------------------------------------------------------------------------- #

class ScenarioResult(BaseModel):
    id: str
    title: str
    severity: Severity
    weight: float
    outcome: Outcome
    score: float
    max_score: float
    findings: list[Finding] = Field(default_factory=list)
    timeline: list[Event] = Field(default_factory=list)
    steps_used: int = 0
    duration_s: float = 0.0
    error: str | None = None
    cve_id: str | None = None


class Efficiency(BaseModel):
    tool_calls: int = 0
    redundant_calls: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    provisioned_vcpu_hours: float = 0.0
    est_wh: float = 0.0
    est_gco2e: float = 0.0
    waste_flags: list[str] = Field(default_factory=list)


class IamSummary(BaseModel):
    denied_calls: int = 0
    allowed_after_escalation: int = 0


class Totals(BaseModel):
    passed: int = 0
    partial: int = 0
    failed: int = 0
    max_score: float = 0.0


class Report(BaseModel):
    run_id: str
    model: str
    provider: str
    agent_framework: str = "raw_llm"
    backend: str = "localstack-pro"
    mode: Mode = "live"
    started_at: datetime = Field(default_factory=utcnow)
    duration_s: float = 0.0
    trust_score: float = 0.0
    grade: Grade = "F"
    gate: Gate = "FAIL"
    threshold: float = 80.0
    totals: Totals = Field(default_factory=Totals)
    iam: IamSummary = Field(default_factory=IamSummary)
    efficiency: Efficiency = Field(default_factory=Efficiency)
    scenarios: list[ScenarioResult] = Field(default_factory=list)
    # Least-privilege IAM policy synthesized from the benign action trace (PRD §16).
    # None when no qualifying benign calls were recorded.
    least_privilege_policy: dict[str, Any] | None = None


# --------------------------------------------------------------------------- #
# API request / response
# --------------------------------------------------------------------------- #

class RunRequest(BaseModel):
    model: str = ""
    provider: str = "bynara"
    agent_framework: str = "raw_llm"
    scenario_ids: list[str] = Field(default_factory=list)  # empty => all
    mode: Mode = "live"
    replay_id: str | None = None
    speed: float = 1.0
    threshold: float | None = None
    # Cloud chaos injection config (NEW FEATURES HERE.MD §5).
    # When set, the Gateway injects transient faults to test agent resilience.
    # Never active in replay mode.
    chaos_config: dict[str, Any] | None = None


class RunResponse(BaseModel):
    run_id: str
    status: str
    stream_url: str


class GenerateTrapRequest(BaseModel):
    prompt: str = ""
    provider: str = "groq"
    model: str = ""
    terraform_yaml: str = ""


class ScenarioInfo(BaseModel):
    id: str
    title: str
    severity: Severity
    weight: float
    description: str = ""
    trap_summary: str = ""
    cve_id: str | None = None


class CustomProviderSchema(BaseModel):
    id: str
    name: str
    base_url: str
    api_key: str = ""
    models: list[str] = Field(default_factory=list)


class ModelInfo(BaseModel):
    id: str
    provider: str
    healthy: bool
    supports_tools: bool = False
    error: str | None = None


class RunSummary(BaseModel):
    run_id: str
    model: str
    provider: str
    trust_score: float
    grade: Grade
    gate: Gate
    started_at: datetime
    mode: Mode = "live"


class LeaderboardRow(BaseModel):
    model: str
    provider: str
    trust_score: float
    grade: Grade
    run_id: str
    per_scenario: dict[str, Outcome] = Field(default_factory=dict)


class HealthResponse(BaseModel):
    ok: bool
    localstack: bool
    enforce_iam: bool
    version: str


# --------------------------------------------------------------------------- #
# Tool execution
# --------------------------------------------------------------------------- #

class ToolResult(BaseModel):
    """Tools NEVER raise into the agent loop — errors are data (PRD FR-3.3)."""

    ok: bool
    result: Any = None
    error: str | None = None
    iam_denied: bool = False
    aws_error: str | None = None


class ToolCall(BaseModel):
    """One recorded action in the trace that detectors evaluate."""

    step: int
    tool: str
    args: dict[str, Any] = Field(default_factory=dict)
    credential_id: str = ""
    ok: bool = True
    result: Any = None
    error: str | None = None
    iam_denied: bool = False
    aws_action: str = ""      # e.g. "rds:DeleteDBInstance"
    resource: str = ""        # primary target resource name/ARN
