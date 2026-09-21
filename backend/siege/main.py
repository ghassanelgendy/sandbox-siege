"""FastAPI application (PRD section 6.9)."""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor

import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sse_starlette.sse import EventSourceResponse

from . import __version__
from .agent.frameworks import get_all_frameworks
from .agent.provider import PROVIDERS, discover_models, health_check_model
from .agent.replay import replay_run
from .cloud import LocalStackBackend
from .events import bus
from .orchestrator import execute_run, list_reports, load_report, new_run_id
from .schemas import (CustomProviderSchema, GenerateTrapRequest, HealthResponse, LeaderboardRow, ModelInfo, Report, RunRequest,
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


@app.post("/api/scenarios/generate", response_model=ScenarioInfo)
def generate_trap(req: GenerateTrapRequest) -> ScenarioInfo:
    from .generator import generate_scenario_from_prompt
    try:
        return generate_scenario_from_prompt(
            prompt=req.prompt,
            provider=req.provider,
            model=req.model,
            terraform_yaml=req.terraform_yaml,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.delete("/api/scenarios/{scenario_id}")
def delete_custom_scenario(scenario_id: str) -> dict:
    from .config import SCENARIOS_DIR
    import re
    # Look in custom scenarios directory
    custom_dir = SCENARIOS_DIR / "custom"
    if not custom_dir.is_dir():
        raise HTTPException(status_code=404, detail="Custom scenarios directory not found")

    target_id = scenario_id.lower().replace("_", "-")
    found_file = None
    for p in custom_dir.glob("*.yaml"):
        # Match either filename stem or internal id
        import yaml
        try:
            doc = yaml.safe_load(p.read_text(encoding="utf-8"))
            if doc.get("id", "").lower() == scenario_id.lower() or p.stem.lower() == target_id:
                found_file = p
                break
        except Exception:
            continue

    if not found_file:
        raise HTTPException(status_code=404, detail=f"Custom scenario {scenario_id!r} not found or is a built-in benchmark scenario")

    found_file.unlink()
    return {"ok": True, "deleted": scenario_id}


@app.get("/api/cves")
def list_catalog_cves() -> list[dict]:
    """Returns curated CVEs mapped to traps with CVSS score, vector, CWE, and ATLAS mappings."""
    from .cve import cve_resolver
    return [{"trap_id": k, **v} for k, v in cve_resolver._catalog.items()]


@app.get("/api/cves/{cve_id}")
def get_cve_details(cve_id: str) -> dict:
    """Resolves live CVE metadata via local catalog, cache, or open vulnerability feeds (OSV/NVD)."""
    from .cve import cve_resolver
    meta = cve_resolver.resolve_for_cve_id(cve_id)
    return {
        "cve_id": meta.cve_id,
        "cvss_score": meta.cvss_score,
        "cvss_vector": meta.cvss_vector,
        "cwe_id": meta.cwe_id,
        "atlas_id": meta.atlas_id,
        "summary": meta.summary,
    }


@app.get("/deck.html")
@app.get("/deck")
def deck() -> FileResponse:
    pkg_deck = os.path.join(os.path.dirname(__file__), "deck.html")
    if os.path.exists(pkg_deck):
        return FileResponse(pkg_deck, media_type="text/html")
    base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    deck_path = os.path.join(base, "presentation", "siege-deck.html")
    if os.path.exists(deck_path):
        return FileResponse(deck_path, media_type="text/html")
    pub_path = os.path.join(base, "frontend", "public", "deck.html")
    if os.path.exists(pub_path):
        return FileResponse(pub_path, media_type="text/html")
    raise HTTPException(status_code=404, detail="Deck presentation file not found")


@app.get("/presentation.html")
@app.get("/presentation")
def presentation() -> FileResponse:
    pkg_presentation = os.path.join(os.path.dirname(__file__), "presentation.html")
    if os.path.exists(pkg_presentation):
        return FileResponse(pkg_presentation, media_type="text/html")
    base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    presentation_path = os.path.join(base, "presentation", "siege-deck-final.html")
    if os.path.exists(presentation_path):
        return FileResponse(presentation_path, media_type="text/html")
    raise HTTPException(status_code=404, detail="Presentation file not found")


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
    from .agent.custom_providers import provider_registry

    all_providers = list(PROVIDERS) + [cp.id for cp in provider_registry.list_providers()]
    pairs = [(provider, model_id)
             for provider in all_providers
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
        res = list(pool.map(_probe, pairs))
    res.sort(key=lambda m: (not m.healthy, not m.supports_tools))
    return res


@app.get("/api/providers")
def get_providers() -> list[dict]:
    from .agent.custom_providers import provider_registry
    from dataclasses import asdict
    return [asdict(p) for p in provider_registry.list_providers()]


@app.post("/api/providers")
def add_custom_provider(req: CustomProviderSchema) -> dict:
    from .agent.custom_providers import CustomProvider, provider_registry
    from dataclasses import asdict
    cp = CustomProvider(
        id=req.id,
        name=req.name,
        base_url=req.base_url,
        api_key=req.api_key,
        models=req.models,
    )
    saved = provider_registry.add_provider(cp)
    return asdict(saved)


@app.delete("/api/providers/{provider_id}")
def delete_custom_provider(provider_id: str) -> dict:
    from .agent.custom_providers import provider_registry
    ok = provider_registry.delete_provider(provider_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Provider not found")
    return {"ok": True, "id": provider_id}


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


@app.post("/api/runs/{run_id}/stop")
async def stop_run(run_id: str) -> dict[str, str]:
    channel = bus.get(run_id)
    if channel is None:
        raise HTTPException(404, f"No active run for {run_id!r}")
    channel.stop()
    return {"status": "stopping", "run_id": run_id}


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
        try:
            events = read_events(run_id)
        except FileNotFoundError:
            raise HTTPException(404, f"No active stream or recorded events for run {run_id!r}")

        async def gen_recorded():
            for event in events:
                yield {"event": event.type, "data": event.model_dump_json()}
            yield {"event": "done", "data": "{}"}

        return EventSourceResponse(gen_recorded())

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
