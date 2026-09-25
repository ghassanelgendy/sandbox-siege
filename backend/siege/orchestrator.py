"""
Run orchestration -- drives scenarios end to end and assembles the Report.

NOTE: this module is not in the original PRD repo layout; it was extracted so the
API, CLI and replay paths share one execution path instead of three. Recorded in
docs/PRD.md decision log as D-12.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

from .cloud import LocalStackBackend
from .cloud.base import CloudBackend
from .config import RUNS_DIR, settings
from .events import RunChannel, bus
from .gateway import Gateway
from .agent.runner import ScenarioRunner
from .agent.provider import ProviderError
from .policy.traps import trap
from .schemas import (Event, EventType, Finding, Report, RunRequest, ScenarioResult, utcnow)
from .scenarios import load_all, load_one
from .scenarios.loader import Scenario
from .chaos import ChaosConfig, ChaosEngine
from .iam_policy import synthesize_least_privilege_policy
from .scoring import (compute_dynamic_threshold, compute_efficiency, decide_outcome, finalize,
                      score_scenario, summarize)


def new_run_id(model: str, mode: str = "live") -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    slug = "".join(c if c.isalnum() else "-" for c in model.split("/")[-1])[:24].strip("-")
    prefix = "replay" if mode == "replay" else "run"
    return f"{prefix}_{stamp}_{slug}"


def _select(scenario_ids: list[str]) -> list[Scenario]:
    if not scenario_ids or scenario_ids == ["ALL"]:
        return load_all()
    return [load_one(sid) for sid in scenario_ids]


def execute_run(req: RunRequest, channel: RunChannel,
                backend: CloudBackend | None = None) -> Report:
    """Run the requested scenarios and return the finished Report."""
    backend = backend or LocalStackBackend()
    scenarios = _select(req.scenario_ids)
    started = time.monotonic()

    threshold = (
        req.threshold
        if req.threshold is not None and req.threshold > 0
        else compute_dynamic_threshold(scenarios)
    )

    report = Report(
        run_id=channel.run_id, model=req.model, provider=req.provider,
        agent_framework=req.agent_framework,
        backend=backend.name, mode="live", started_at=utcnow(),
        threshold=threshold,
    )

    channel.emit(EventType.RUN_STARTED, {
        "model": req.model, "provider": req.provider,
        "agent_framework": req.agent_framework,
        "scenario_ids": [s.id for s in scenarios], "backend": backend.name,
    })

    total_vcpu_hours = 0.0
    total_tokens_in = total_tokens_out = 0
    all_trace = []
    waste_flags: list[str] = []

    for scenario in scenarios:
        if channel.stopped:
            break
        result = _run_scenario(scenario, req, channel, backend)
        report.scenarios.append(result)

        gw = result.__dict__.pop("_gateway", None)
        if gw is not None:
            total_vcpu_hours += gw.ctx.provisioned_vcpu_hours
            all_trace.extend(gw.trace)
            report.iam.denied_calls += gw.iam_denied_calls
            report.iam.allowed_after_escalation += gw.calls_after_escalation
            for call in gw.trace:
                if call.tool == "ec2_run_instances" and call.ok:
                    itype = str(call.args.get("instance_type", ""))
                    if itype and not itype.startswith(("t3.nano", "t3.micro", "t3.small")):
                        waste_flags.append(f"oversized_instance:{itype}")
        for tag in result.__dict__.pop("_models_used", []):
            if tag not in report.models_used:
                report.models_used.append(tag)
        total_tokens_in += result.__dict__.pop("_tokens_in", 0)
        total_tokens_out += result.__dict__.pop("_tokens_out", 0)

    report.efficiency = compute_efficiency(
        all_trace, tokens_in=total_tokens_in, tokens_out=total_tokens_out,
        provisioned_vcpu_hours=total_vcpu_hours, waste_flags=waste_flags,
    )

    # Synthesize least-privilege policy from the full benign trace (PRD §16)
    all_findings = [f for s in report.scenarios for f in s.findings]
    # Determine the primary granted credential id (first scenario's or a fallback)
    primary_cred_id = scenarios[0].credential_id if scenarios else ""
    report.least_privilege_policy = synthesize_least_privilege_policy(
        all_trace, all_findings, primary_cred_id
    )

    report.duration_s = round(time.monotonic() - started, 2)
    finalize(report)

    channel.emit(EventType.RUN_FINISHED, {
        "trust_score": report.trust_score, "grade": report.grade,
        "gate": report.gate, "summary": summarize(report),
    })
    _persist(report)
    channel.close()
    return report


def _run_scenario(scenario: Scenario, req: RunRequest, channel: RunChannel,
                  backend: CloudBackend) -> ScenarioResult:
    started = time.monotonic()
    first_seq = channel._seq + 1

    result = ScenarioResult(
        id=scenario.id, title=scenario.title, severity=scenario.severity,
        weight=scenario.weight, outcome="fail", score=0.0, max_score=float(scenario.weight),
        cve_id=scenario.cve_id,
    )

    try:
        backend.reset()
        scenario.setup(backend)
    except Exception as exc:  # noqa: BLE001
        result.error = f"setup failed: {exc}"
        channel.emit(EventType.RUN_ERROR, {"message": result.error, "scenario_id": scenario.id})
        return result

    channel.emit(EventType.SCENARIO_STARTED, {
        "scenario_id": scenario.id, "title": scenario.title, "severity": scenario.severity,
        "task_prompt": scenario.task_prompt.strip(), "credential": scenario.credential_id,
    }, scenario_id=scenario.id)
    # A resource that failed to seed means its trap may be unreachable -- say so on the
    # stream instead of letting the scenario read as a clean pass (D-55).
    for err in scenario.seed_errors:
        channel.emit(EventType.RUN_ERROR, {"message": f"seed failed: {err}",
                                           "scenario_id": scenario.id}, scenario_id=scenario.id)

    chaos_cfg: ChaosConfig | None = None
    if req.chaos_config and req.mode != "replay":
        chaos_cfg = ChaosConfig.from_dict(req.chaos_config)
    gw = Gateway(backend, scenario, channel, chaos_config=chaos_cfg)
    runner = ScenarioRunner(gw, req.provider, req.model, agent_framework=req.agent_framework)

    try:
        runner.run()
        # Jev advisory evaluation runs once after the full trace is complete (D-43)
        gw.run_jev_evaluation()
    except ProviderError as exc:
        result.error = str(exc)
        channel.emit(EventType.RUN_ERROR, {"message": result.error, "scenario_id": scenario.id})
    except Exception as exc:  # noqa: BLE001
        result.error = f"runner failed: {exc}"
        channel.emit(EventType.RUN_ERROR, {"message": result.error, "scenario_id": scenario.id})
    finally:
        scenario.teardown(backend)

    if result.error:
        info = trap("LLM-FAILURE")
        gw.add_finding(Finding(
            trap_id="LLM-FAILURE", severity="CRITICAL", title=info.title,
            evidence=result.error, explanation=f"Execution error: {result.error}",
            remediation=info.remediation, step=gw.step,
        ))
        result.findings = gw.findings
        result.outcome = "fail"
        result.score = 0.0
    else:
        result.findings = gw.findings
        result.outcome = decide_outcome(gw.findings, scenario.outcome_rules)
        result.score = score_scenario(scenario.weight, result.outcome)

    result.steps_used = gw.step
    result.duration_s = round(time.monotonic() - started, 2)
    result.timeline = [e for e in channel.buffer if e.seq >= first_seq]

    channel.emit(EventType.SCENARIO_FINISHED, {
        "scenario_id": scenario.id, "outcome": result.outcome,
        "score": result.score, "max_score": result.max_score,
        "findings": [f.model_dump(mode="json") for f in result.findings],
    }, scenario_id=scenario.id)

    # carried out-of-band so execute_run can aggregate without re-walking
    result.__dict__["_gateway"] = gw
    result.__dict__["_models_used"] = list(runner.models_used)
    result.__dict__["_tokens_in"] = runner.tokens_in
    result.__dict__["_tokens_out"] = runner.tokens_out
    return result


def _persist(report: Report) -> None:
    d = RUNS_DIR / report.run_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "report.json").write_text(
        report.model_dump_json(indent=2) + "\n", encoding="utf-8")


def load_report(run_id: str) -> Report | None:
    for base in (RUNS_DIR, RUNS_DIR / "seeded"):
        p = base / run_id / "report.json"
        if p.exists():
            return Report.model_validate_json(p.read_text(encoding="utf-8"))
    return None


def list_reports() -> list[Report]:
    out: list[Report] = []
    for base in (RUNS_DIR, RUNS_DIR / "seeded"):
        if not base.exists():
            continue
        for d in sorted(base.iterdir()):
            p = d / "report.json"
            if p.exists():
                try:
                    out.append(Report.model_validate_json(p.read_text(encoding="utf-8")))
                except Exception:
                    continue
    return sorted(out, key=lambda r: r.started_at, reverse=True)
