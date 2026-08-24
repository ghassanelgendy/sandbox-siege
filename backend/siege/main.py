"""FastAPI application (PRD section 6.9)."""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse

from . import __version__
from .agent.frameworks import get_all_frameworks
from .agent.provider import PROVIDERS, discover_models, health_check_model
from .agent.replay import replay_run
from .cloud import LocalStackBackend
from .events import bus
from .orchestrator import execute_run, list_reports, load_report, new_run_id
from .schemas import (HealthResponse, LeaderboardRow, ModelInfo, Report, RunRequest,
                      RunResponse, RunSummary, ScenarioInfo)
from .scenarios import scenario_infos

app = FastAPI(title="Sandbox Siege", version=__version__)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)

_pool = ThreadPoolExecutor(max_workers=2)
_backend = LocalStackBackend()
_enforce_iam_cache: bool | None = None


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    global _enforce_iam_cache
    up = _backend.health()
    if up and _enforce_iam_cache is None:
        _enforce_iam_cache = _backend.enforce_iam_active()
    return HealthResponse(ok=up, localstack=up,
                          enforce_iam=bool(_enforce_iam_cache), version=__version__)


@app.get("/api/scenarios", response_model=list[ScenarioInfo])
def scenarios() -> list[ScenarioInfo]:
    return scenario_infos()


@app.get("/api/agents")
def agents() -> list[dict]:
    return get_all_frameworks()


@app.get("/api/models", response_model=list[ModelInfo])
def models(probe: bool = True) -> list[ModelInfo]:
    """Discovered at runtime and health-checked -- never hardcoded (FR-4.7).

    Probes run concurrently: a roster of 50+ models, each a real tool-calling
    request, is minutes of wall-clock done serially -- long enough that the UI's
    fetch gives up. Order is preserved so the selector stays grouped by provider.
    """
    pairs = [(provider, model_id)
             for provider in PROVIDERS
             for model_id in discover_models(provider)]

    if not probe:
        return [ModelInfo(id=mid, provider=prov, healthy=True) for prov, mid in pairs]

    def _probe(pair: tuple[str, str]) -> ModelInfo:
        prov, mid = pair
        probed = health_check_model(prov, mid)
        return ModelInfo(id=mid, provider=prov, healthy=probed["healthy"],
                         supports_tools=probed["supports_tools"], error=probed["error"])

    if not pairs:
        return []
    with ThreadPoolExecutor(max_workers=min(12, len(pairs))) as pool:
        return list(pool.map(_probe, pairs))


@app.post("/api/runs", response_model=RunResponse)
async def create_run(req: RunRequest) -> RunResponse:
    if req.mode == "replay":
        if not req.replay_id:
            raise HTTPException(400, "replay mode requires replay_id")
        source = load_report(req.replay_id)
        run_id = new_run_id(source.model if source else "replay", "replay")
        channel = bus.create(run_id)
        asyncio.create_task(replay_run(req.replay_id, channel, req.speed))
    else:
        if not req.model:
            raise HTTPException(400, "model is required for a live run")
        run_id = new_run_id(req.model)
        channel = bus.create(run_id)
        loop = asyncio.get_running_loop()
        loop.run_in_executor(_pool, execute_run, req, channel, _backend)

    return RunResponse(run_id=run_id, status="running",
                       stream_url=f"/api/runs/{run_id}/stream")


@app.get("/api/runs", response_model=list[RunSummary])
def runs() -> list[RunSummary]:
    return [RunSummary(run_id=r.run_id, model=r.model, provider=r.provider,
                       trust_score=r.trust_score, grade=r.grade, gate=r.gate,
                       started_at=r.started_at, mode=r.mode)
            for r in list_reports()]


@app.get("/api/runs/{run_id}", response_model=Report)
def run_report(run_id: str) -> Report:
    report = load_report(run_id)
    if report is None:
        raise HTTPException(404, f"No report for run {run_id!r}")
    return report


@app.get("/api/runs/{run_id}/stream")
async def stream(run_id: str) -> EventSourceResponse:
    channel = bus.get(run_id)
    if channel is None:
        raise HTTPException(404, f"No active stream for run {run_id!r}")

    async def gen():
        q = channel.subscribe()
        try:
            while True:
                event = await q.get()
                if event is None:
                    yield {"event": "done", "data": "{}"}
                    return
                yield {"event": event.type, "data": event.model_dump_json()}
        finally:
            channel.unsubscribe(q)

    return EventSourceResponse(gen())


@app.get("/api/leaderboard", response_model=list[LeaderboardRow])
def leaderboard() -> list[LeaderboardRow]:
    best: dict[str, Report] = {}
    for r in list_reports():
        key = f"{r.provider}/{r.model}"
        if key not in best or r.trust_score > best[key].trust_score:
            best[key] = r
    rows = [LeaderboardRow(model=r.model, provider=r.provider, trust_score=r.trust_score,
                           grade=r.grade, run_id=r.run_id,
                           per_scenario={s.id: s.outcome for s in r.scenarios})
            for r in best.values()]
    return sorted(rows, key=lambda x: x.trust_score, reverse=True)
