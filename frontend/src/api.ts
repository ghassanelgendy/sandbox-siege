/**
 * API client with a fixture fallback.
 *
 * Every read falls back to the frozen fixture when the backend is unreachable,
 * so the UI can be built and demonstrated independently (PRD FR-U.4).
 */

import fixture from "./fixture.json";
import type {
  CustomProvider, HealthResponse, LeaderboardRow, ModelInfo, Report, RunResponse,
  ScenarioInfo, SiegeEvent,
} from "./types";

const BASE = "/api";

async function get<T>(path: string, fallback: T): Promise<T> {
  try {
    const r = await fetch(`${BASE}${path}`);
    if (!r.ok) throw new Error(String(r.status));
    return (await r.json()) as T;
  } catch {
    return fallback;
  }
}

export const sampleReport = fixture as unknown as Report;

export const getHealth = () =>
  get<HealthResponse>("/health", { ok: false, localstack: false, enforce_iam: false, version: "—" });

export const getScenarios = () =>
  get<ScenarioInfo[]>("/scenarios", sampleReport.scenarios.map((s) => ({
    id: s.id, title: s.title, severity: s.severity, weight: s.weight,
    description: "", trap_summary: "",
  })));

export async function generateTrap(prompt: string, provider = "groq", model = ""): Promise<ScenarioInfo | null> {
  try {
    const r = await fetch(`${BASE}/scenarios/generate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prompt, provider, model }),
    });
    if (!r.ok) return null;
    return (await r.json()) as ScenarioInfo;
  } catch {
    return null;
  }
}

export const getModels = () => get<ModelInfo[]>("/models", []);

export const getCustomProviders = () => get<CustomProvider[]>("/providers", []);

export async function addCustomProvider(provider: CustomProvider): Promise<CustomProvider | null> {
  try {
    const r = await fetch(`${BASE}/providers`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(provider),
    });
    if (!r.ok) return null;
    return (await r.json()) as CustomProvider;
  } catch {
    return null;
  }
}

export async function deleteCustomProvider(id: string): Promise<boolean> {
  try {
    const r = await fetch(`${BASE}/providers/${id}`, { method: "DELETE" });
    return r.ok;
  } catch {
    return false;
  }
}

export interface AgentFramework {
  id: string;
  name: string;
  description: string;
  github_url: string;
  tools: string[];
  system_prompt: string;
}

export const getAgents = () => get<AgentFramework[]>("/agents", []);

export const getReport = (runId: string) => get<Report | null>(`/runs/${runId}`, null);

export const getLeaderboard = () => get<LeaderboardRow[]>("/leaderboard", []);

export async function startRun(body: Record<string, unknown>): Promise<RunResponse | null> {
  try {
    const r = await fetch(`${BASE}/runs`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!r.ok) throw new Error(String(r.status));
    return (await r.json()) as RunResponse;
  } catch {
    return null;
  }
}

export async function stopRun(runId: string): Promise<boolean> {
  try {
    const r = await fetch(`${BASE}/runs/${runId}/stop`, { method: "POST" });
    return r.ok;
  } catch {
    return false;
  }
}

/** Live SSE stream. Returns a disposer. */
export function streamRun(
  runId: string,
  onEvent: (e: SiegeEvent) => void,
  onDone: () => void,
): () => void {
  const es = new EventSource(`${BASE}/runs/${runId}/stream`);
  const handle = (ev: MessageEvent) => {
    try { onEvent(JSON.parse(ev.data) as SiegeEvent); } catch { /* ignore malformed frame */ }
  };
  // the server names each frame after its event type
  for (const t of ["run.started", "scenario.started", "agent.message", "tool.called",
                   "iam.verdict", "policy.verdict", "tool.result", "trap.triggered",
                   "scenario.finished", "run.finished", "run.error"]) {
    es.addEventListener(t, handle as EventListener);
  }
  es.addEventListener("done", () => { es.close(); onDone(); });
  es.onerror = () => { es.close(); onDone(); };
  return () => es.close();
}

/**
 * Replays the fixture's recorded timelines as a fake stream.
 * Lets the console be built and rehearsed with no backend at all.
 */
export function streamFixture(
  onEvent: (e: SiegeEvent) => void,
  onDone: () => void,
  speedMs = 260,
): () => void {
  const events: SiegeEvent[] = sampleReport.scenarios.flatMap((s) => s.timeline);
  let i = 0;
  let cancelled = false;
  const tick = () => {
    if (cancelled) return;
    if (i >= events.length) { onDone(); return; }
    onEvent(events[i++]);
    const gap = events[i - 1]?.type === "trap.triggered" ? speedMs * 3.5 : speedMs;
    setTimeout(tick, gap);
  };
  setTimeout(tick, 400);
  return () => { cancelled = true; };
}
