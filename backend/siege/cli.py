"""Sandbox Siege CLI (PRD section 6.10)."""

from __future__ import annotations

import asyncio
import os
import sys

import typer
from rich.console import Console
from rich.table import Table

from . import __version__
from .agent.frameworks_acme import register as _register_acme
from .agent.provider import PROVIDERS, discover_models, health_check_model
from .agent.replay import replay_run
from .cloud import LocalStackBackend
from .config import settings
from .events import bus
from .orchestrator import execute_run, load_report, new_run_id
from .schemas import Report, RunRequest
from .scenarios import load_all
from .scoring import summarize

app = typer.Typer(add_completion=False, help="Chaos engineering for AI agents.")
console = Console()

OUTCOME_STYLE = {"pass": ("PASS", "green"), "partial": ("WARN", "yellow"), "fail": ("FAIL", "red")}
GRADE_STYLE = {"A": "green", "B": "green", "C": "yellow", "D": "yellow", "F": "red"}

# Acme overlay: make acme_secure / acme_insecure frameworks (and the hooking
# runner) available to every command.
_register_acme()


def _print_report(report: Report) -> None:
    console.print()
    console.rule(f"[bold]SANDBOX SIEGE[/bold] — {report.run_id}")
    console.print(f"Model: [cyan]{report.model}[/cyan] ({report.provider})   "
                  f"Framework: [cyan]{report.agent_framework}[/cyan]   "
                  f"Backend: {report.backend}   Mode: {report.mode}")
    console.print()

    table = Table(show_header=True, header_style="bold", box=None, pad_edge=False)
    for col, just in (("Scenario", "left"), ("Title", "left"), ("Result", "left"),
                      ("Score", "right"), ("Findings", "left")):
        table.add_column(col, justify=just)

    for s in report.scenarios:
        label, colour = OUTCOME_STYLE[s.outcome]
        traps = ", ".join(f.trap_id for f in s.findings if f.severity != "INFO") or "—"
        table.add_row(s.id, s.title, f"[{colour}]{label}[/{colour}]",
                      f"{s.score:g}/{s.max_score:g}", traps)
    console.print(table)

    gcol = GRADE_STYLE.get(report.grade, "white")
    gate_col = "green" if report.gate == "PASS" else "red"
    console.print()
    console.print(f"  TRUST SCORE  [bold]{report.trust_score:g}[/bold]/100   "
                  f"GRADE [bold {gcol}]{report.grade}[/bold {gcol}]   "
                  f"GATE [bold {gate_col}]{report.gate}[/bold {gate_col}] "
                  f"(threshold {report.threshold:g})")
    e = report.efficiency
    console.print(f"  Efficiency   {e.tool_calls} calls ({e.redundant_calls} redundant)   "
                  f"{e.tokens_in + e.tokens_out} tokens   "
                  f"~{e.est_wh:g} Wh / {e.est_gco2e:g} gCO2e")
    console.print(f"  IAM          {report.iam.denied_calls} denied, "
                  f"{report.iam.allowed_after_escalation} allowed after escalation")
    console.print(f"  {summarize(report)}")
    console.print()


@app.command()
def doctor() -> None:
    """Check every precondition before a demo. Exit 0 only if all criticals pass."""
    console.print(f"\n[bold]Sandbox Siege doctor[/bold]  v{__version__}\n")
    table = Table(show_header=True, header_style="bold", box=None)
    table.add_column("Check"); table.add_column("Status"); table.add_column("Detail")

    critical_ok = True
    backend = LocalStackBackend()

    up = backend.health()
    critical_ok &= up
    table.add_row("LocalStack", "[green]OK[/green]" if up else "[red]FAIL[/red]",
                  backend.endpoint_url if up else "not reachable — run `make up`")

    if up:
        detail = backend.health_detail().get("services", {})
        need = ["s3", "dynamodb", "rds", "ec2", "logs", "secretsmanager", "ssm", "iam"]
        missing = [s for s in need if s not in detail]
        table.add_row("Services", "[green]OK[/green]" if not missing else "[yellow]PARTIAL[/yellow]",
                      f"{len(need) - len(missing)}/{len(need)} available"
                      + (f" — missing {', '.join(missing)}" if missing else ""))

        enforced = backend.enforce_iam_active()
        table.add_row("ENFORCE_IAM", "[green]active[/green]" if enforced else "[yellow]INACTIVE[/yellow]",
                      "permission layer is real" if enforced
                      else "L1 disabled — behavioural detectors still work")

    scenarios = load_all()
    weight = sum(s.weight for s in scenarios)
    weight_ok = weight > 0
    critical_ok &= weight_ok
    table.add_row("Scenarios", "[green]OK[/green]" if weight_ok else "[red]FAIL[/red]",
                  f"{len(scenarios)} loaded, total weight {weight} (normalized at runtime)")

    any_provider = False
    for provider in PROVIDERS:
        _, key = settings.provider_config(provider)
        if not key:
            table.add_row(f"Provider {provider}", "[yellow]SKIP[/yellow]", "no API key in .env")
            continue
        found = discover_models(provider)
        any_provider |= bool(found)
        table.add_row(f"Provider {provider}", "[green]OK[/green]" if found else "[red]FAIL[/red]",
                      f"{len(found)} models" if found else "unreachable")
    critical_ok &= any_provider

    # NFR-7: refuse to look like it might touch real AWS
    risky = [v for v in ("AWS_PROFILE", "AWS_ACCESS_KEY_ID")
             if os.environ.get(v) and not os.environ.get(v, "").startswith("test")]
    table.add_row("Real-AWS guard", "[green]OK[/green]" if not risky else "[red]WARN[/red]",
                  "no real AWS credentials in env" if not risky
                  else f"{', '.join(risky)} set — unset before running")

    console.print(table)
    console.print()
    raise typer.Exit(0 if critical_ok else 1)


@app.command()
def models(provider: str = typer.Option("", help="Limit to one provider"),
           probe: bool = typer.Option(True, help="Health-check each model")) -> None:
    """List models discovered from the providers, with tool-calling support."""
    table = Table(show_header=True, header_style="bold", box=None)
    table.add_column("Model"); table.add_column("Provider")
    table.add_column("Health"); table.add_column("Tools"); table.add_column("Note")

    for prov in ([provider] if provider else list(PROVIDERS)):
        for mid in discover_models(prov):
            if not probe:
                table.add_row(mid, prov, "—", "—", "")
                continue
            r = health_check_model(prov, mid)
            table.add_row(
                mid, prov,
                "[green]OK[/green]" if r["healthy"] else "[red]DOWN[/red]",
                "[green]yes[/green]" if r["supports_tools"] else "[yellow]text[/yellow]",
                (r["error"] or "")[:60])
    console.print(table)


def _load_framework_file(path: str) -> str:
    """Load a python file that defines a `framework` dict and register it."""
    import importlib.util

    from .agent.frameworks import AgentFrameworkInfo, FRAMEWORKS

    spec = importlib.util.spec_from_file_location("siege_custom_framework", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    md = getattr(mod, "framework", None)
    if not isinstance(md, dict) or not md.get("id"):
        raise ValueError(
            f"--framework-file {path}: the module must define `framework = "
            "{'id': ..., 'system_prompt': ..., ...}`")
    fid = str(md["id"])
    FRAMEWORKS[fid] = AgentFrameworkInfo(
        id=fid,
        name=str(md.get("name", fid)),
        description=str(md.get("description", "")),
        github_url=str(md.get("github_url", "")),
        tools=list(md.get("tools") or []),
        system_prompt=str(md.get("system_prompt", "")),
    )
    console.print(f"[dim]loaded framework '{fid}' from {path}[/dim]")
    return fid


@app.command()
def run(model: str = typer.Option(..., help="Model id, e.g. deepseek-v4-pro-free"),
        provider: str = typer.Option("bynara", help="bynara | dahl | groq"),
        framework: str = typer.Option("raw_llm", "--framework", "-fw",
                                       help="Agent framework id (raw_llm | acme_secure | acme_insecure)"),
        framework_file: str = typer.Option(None, "--framework-file",
                                           help="Load a python module defining `framework` dict"),
        scenario: list[str] = typer.Option([], help="Scenario id (repeatable)"),
        all_scenarios: bool = typer.Option(False, "--all", help="Run every scenario"),
        threshold: float = typer.Option(None, help="Gate threshold (0-100, or omit/0 for dynamic severity-risk-adaptive)"),
        format: str = typer.Option("text", "--format", "-f", help="Output format: text | json")) -> None:
    """Run the siege. Exits non-zero if the gate fails (FR-11.1)."""
    ids = [] if all_scenarios else list(scenario)
    if framework_file:
        framework = _load_framework_file(framework_file)
    req = RunRequest(model=model, provider=provider, scenario_ids=ids,
                     agent_framework=framework,
                     threshold=threshold if threshold is not None and threshold > 0 else None)
    run_id = new_run_id(model)
    channel = bus.create(run_id)
    if format == "json":
        report = execute_run(req, channel)
        print(report.model_dump_json(indent=2))
    else:
        console.print(f"[dim]run {run_id} — streaming to runs/{run_id}/events.jsonl[/dim]")
        report = execute_run(req, channel)
        _print_report(report)
    raise typer.Exit(0 if report.gate == "PASS" else 1)


@app.command()
def replay(run_id: str = typer.Argument(..., help="Recorded run id"),
           speed: float = typer.Option(1.0, help="Playback speed multiplier")) -> None:
    """Replay a recorded run. No network, no sandbox (FR-8.3)."""
    new_id = new_run_id(run_id, "replay")
    channel = bus.create(new_id)
    report = asyncio.run(replay_run(run_id, channel, speed))
    if report is None:
        console.print(f"[red]No report found for {run_id}[/red]")
        raise typer.Exit(1)
    _print_report(report)


@app.command()
def seed(models_csv: str = typer.Option(
            "deepseek-v4-pro-free:bynara,mistral-large:bynara,"
            "moonshotai/Kimi-K2.6:dahl,MiniMaxAI/MiniMax-M2.7:dahl",
            "--models", help="Comma-separated model:provider pairs")) -> None:
    """Run the full suite for several models to populate the leaderboard."""
    for pair in [p for p in models_csv.split(",") if p.strip()]:
        model, _, provider = pair.rpartition(":")
        model, provider = model.strip(), provider.strip() or "bynara"
        console.print(f"\n[bold]Sieging {model} ({provider})[/bold]")
        try:
            channel = bus.create(new_run_id(model))
            report = execute_run(RunRequest(model=model, provider=provider), channel)
            _print_report(report)
        except Exception as exc:  # noqa: BLE001
            console.print(f"[red]{model}: {exc}[/red]")


@app.command()
def scenarios() -> None:
    """List the trap library."""
    table = Table(show_header=True, header_style="bold", box=None)
    table.add_column("ID"); table.add_column("Title"); table.add_column("Sev")
    table.add_column("Wt", justify="right"); table.add_column("The question it asks")
    for s in load_all():
        table.add_row(s.id, s.title, s.severity, str(s.weight),
                      " ".join(s.trap_summary.split()))
    console.print(table)


if __name__ == "__main__":
    app()