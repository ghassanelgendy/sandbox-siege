import { useEffect, useState } from "react";
import { Play, ShieldAlert, Compass, Sparkles, Loader2, Plus, Settings } from "lucide-react";
import { getHealth, getModels, getScenarios, getAgents, generateTrap, addCustomProvider, AgentFramework } from "../api";
import { Chip, Empty, Eyebrow, Panel } from "../components/Bits";
import AgentNavigator from "../components/AgentNavigator";
import type { HealthResponse, ModelInfo, ScenarioInfo } from "../types";

export default function Launch({ onLaunch }: {
  onLaunch: (opts: { model: string; provider: string; agentFramework: string; scenarioIds: string[];
                     threshold: number; demo: boolean }) => void;
}) {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [scenarios, setScenarios] = useState<ScenarioInfo[]>([]);
  const [agentsList, setAgentsList] = useState<AgentFramework[]>([]);
  const [agentNavOpen, setAgentNavOpen] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [model, setModel] = useState("");
  const [agentFramework, setAgentFramework] = useState("raw_llm");
  const [threshold, setThreshold] = useState(80);
  const [loading, setLoading] = useState(true);
  const [modelsLoading, setModelsLoading] = useState(true);

  // AI Trap generation modal state
  const [aiModalOpen, setAiModalOpen] = useState(false);
  const [trapPrompt, setTrapPrompt] = useState("");
  const [isGenerating, setIsGenerating] = useState(false);
  const [genError, setGenError] = useState<string | null>(null);

  // Custom Provider modal state
  const [providerModalOpen, setProviderModalOpen] = useState(false);
  const [newProvId, setNewProvId] = useState("");
  const [newProvName, setNewProvName] = useState("");
  const [newProvUrl, setNewProvUrl] = useState("");
  const [newProvKey, setNewProvKey] = useState("");
  const [newProvModels, setNewProvModels] = useState("");
  const [provSaving, setProvSaving] = useState(false);
  const [provError, setProvError] = useState<string | null>(null);

  useEffect(() => {
    getHealth().then(setHealth);
    getAgents().then(setAgentsList);
    getScenarios().then((s) => {
      setScenarios(s);
      setSelected(new Set(s.map((x) => x.id)));
      setLoading(false);
    });
    getModels().then((m) => {
      const sorted = [...m].sort((a, b) => {
        if (a.healthy !== b.healthy) return a.healthy ? -1 : 1;
        if (a.supports_tools !== b.supports_tools) return a.supports_tools ? -1 : 1;
        return 0;
      });
      setModels(sorted);
      const first = sorted.find((x) => x.healthy && x.supports_tools) ?? sorted.find((x) => x.healthy);
      if (first) setModel(`${first.provider}/${first.id}`);
      setModelsLoading(false);
    });
  }, []);

  const toggle = (id: string) => setSelected((prev) => {
    const next = new Set(prev);
    next.has(id) ? next.delete(id) : next.add(id);
    return next;
  });

  const launch = (demo: boolean) => {
    const [provider, ...rest] = model.split("/");
    onLaunch({
      model: rest.join("/"), provider: provider || "bynara",
      agentFramework,
      scenarioIds: [...selected], threshold, demo,
    });
  };

  return (
    <div className="mx-auto max-w-5xl px-8 py-14">
      <Eyebrow>Pre-production agent safety</Eyebrow>
      <h1 className="mt-2 max-w-3xl font-display text-5xl leading-[1.05] font-semibold text-ink">
        We are all hiring autonomous agents.
        <span className="text-ink-mute"> Nobody interviews them.</span>
      </h1>
      <p className="mt-4 max-w-2xl leading-relaxed text-ink-dim">
        Sandbox Siege runs an agent against a real AWS emulator seeded with deliberate
        traps, watches every action it takes, and returns a trust score you can gate on.
      </p>

      {/* environment */}
      <Panel className="mt-10 p-5">
        <div className="flex flex-wrap items-center gap-x-8 gap-y-3">
          <div>
            <Eyebrow>Sandbox</Eyebrow>
            <div className="mt-1 flex items-center gap-2">
              <Chip tone={health?.localstack ? "jade" : "sand"}>
                {health?.localstack ? "LocalStack up" : "LocalStack down"}
              </Chip>
              <Chip tone={health?.enforce_iam ? "jade" : "mute"}>
                {health?.enforce_iam ? "ENFORCE_IAM active" : "ENFORCE_IAM off"}
              </Chip>
            </div>
          </div>
          <div className="flex-[2] min-w-[320px] flex gap-4">
            <div className="flex-1">
              <div className="flex items-center justify-between">
                <Eyebrow>Agent model</Eyebrow>
                <button
                  type="button"
                  onClick={() => setProviderModalOpen(true)}
                  className="font-mono text-[11px] text-sand hover:text-sand-lit flex items-center gap-1"
                >
                  <Plus size={11} /> + Add LLM
                </button>
              </div>
              <select value={model} onChange={(e) => setModel(e.target.value)}
                      className="mt-1 w-full border border-rule bg-ground px-3 py-2
                                 font-mono text-sm text-ink">
                {models.length === 0 && (
                  <option value="">
                    {modelsLoading ? "Probing models…" : "No models reachable"}
                  </option>
                )}
                {models.map((m) => (
                  <option key={`${m.provider}/${m.id}`} value={`${m.provider}/${m.id}`}
                          disabled={!m.healthy}>
                    {m.id} · {m.provider}
                    {!m.healthy ? " — unavailable" : m.supports_tools ? "" : " — text protocol"}
                  </option>
                ))}
              </select>
            </div>
            <div className="flex-1">
              <div className="flex items-center justify-between">
                <Eyebrow>Agent framework</Eyebrow>
                <button
                  type="button"
                  onClick={() => setAgentNavOpen(true)}
                  className="inline-flex items-center gap-1 font-mono text-[10px] text-sand hover:underline"
                >
                  <Compass size={11} /> Agent Navigator
                </button>
              </div>
              <select value={agentFramework} onChange={(e) => setAgentFramework(e.target.value)}
                      className="mt-1 w-full border border-rule bg-ground px-3 py-2
                                 font-mono text-sm text-ink">
                <option value="raw_llm">Raw LLM (internal loop)</option>
                <option value="swe_agent">SWE-agent (Princeton)</option>
                <option value="crewai">CrewAI (Multi-Agent)</option>
                <option value="autogpt">AutoGPT (Autonomous)</option>
                <option value="opscode">OpsCode (DevOps Agent)</option>
                <option value="opensre">OpenSRE (Incident SRE)</option>
                <option value="k8sgpt">K8sGPT (Kubernetes SRE)</option>
                <option value="insecure">Insecure Bot (Showcase Target)</option>
              </select>
            </div>
          </div>
          <div>
            <Eyebrow>Gate threshold</Eyebrow>
            <input type="number" min={0} max={100} value={threshold}
                   onChange={(e) => setThreshold(Number(e.target.value))}
                   className="mt-1 w-24 border border-rule bg-ground px-3 py-2
                              font-mono text-sm text-ink" />
          </div>
        </div>
      </Panel>

      {/* trap library */}
      <div className="mt-10 flex items-baseline justify-between">
        <div className="flex items-center gap-3">
          <Eyebrow>Trap library — {selected.size} of {scenarios.length} selected</Eyebrow>
          <button
            type="button"
            onClick={() => setAiModalOpen(true)}
            className="inline-flex items-center gap-1.5 border border-sand/40 bg-sand/10 px-2.5 py-1
                       font-display text-[11px] font-semibold uppercase tracking-wider text-sand hover:bg-sand/20 transition-colors"
          >
            <Sparkles size={13} />
            Add Trap with AI
          </button>
        </div>
        <button onClick={() => setSelected(new Set(scenarios.map((s) => s.id)))}
                className="font-mono text-[11px] text-ink-mute hover:text-ink">select all</button>
      </div>

      {loading ? (
        <div className="mt-3 space-y-2">
          {[0, 1, 2].map((i) => <div key={i} className="h-16 animate-pulse border border-rule bg-panel" />)}
        </div>
      ) : scenarios.length === 0 ? (
        <div className="mt-3"><Empty title="No scenarios loaded" hint="Check backend/siege/scenarios/" /></div>
      ) : (
        <div className="mt-3 divide-y divide-rule border border-rule">
          {scenarios.map((s) => {
            const on = selected.has(s.id);
            return (
              <button key={s.id} onClick={() => toggle(s.id)}
                      className={`flex w-full items-start gap-4 p-4 text-left transition-colors
                                  ${on ? "bg-panel" : "bg-transparent opacity-45"}`}>
                <span className={`mt-1 h-3 w-3 shrink-0 border
                                  ${on ? "border-sand bg-sand" : "border-rule-lit"}`} />
                <span className="min-w-0 flex-1">
                  <span className="flex items-baseline gap-2">
                    <span className="font-mono text-[11px] text-ink-mute">{s.id}</span>
                    <span className="font-display text-base text-ink">{s.title}</span>
                  </span>
                  {s.trap_summary && (
                    <span className="mt-0.5 block text-sm text-ink-dim">{s.trap_summary}</span>
                  )}
                </span>
                <span className="shrink-0 font-mono text-[11px] text-ink-mute">
                  {s.severity} · {s.weight}
                </span>
              </button>
            );
          })}
        </div>
      )}

      <div className="mt-8 flex flex-wrap items-center gap-3">
        <button onClick={() => launch(false)} disabled={!model || selected.size === 0}
                className="inline-flex items-center gap-2 border border-sand bg-sand
                           px-6 py-3 font-display font-semibold tracking-wide text-ground
                           disabled:cursor-not-allowed disabled:opacity-40">
          <Play size={16} /> Launch siege
        </button>
        <button onClick={() => launch(true)}
                className="inline-flex items-center gap-2 border border-rule-lit px-5 py-3
                           font-display tracking-wide text-ink-dim hover:text-ink">
          <ShieldAlert size={16} /> Demo replay
        </button>
        <p className="text-sm text-ink-mute">
          Demo replay streams a recorded run — no network, no sandbox.
        </p>
      </div>

      <AgentNavigator
        agents={agentsList}
        isOpen={agentNavOpen}
        onClose={() => setAgentNavOpen(false)}
        onSelectAgent={(id) => setAgentFramework(id)}
      />

      {/* AI Trap Creator Modal */}
      {aiModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-ground/80 backdrop-blur-sm p-4">
          <div className="w-full max-w-xl border border-rule-lit bg-panel p-6 shadow-2xl">
            <div className="flex items-center justify-between pb-4 border-b border-rule">
              <div className="flex items-center gap-2">
                <Sparkles className="text-sand" size={18} />
                <h3 className="font-display text-lg font-semibold text-ink">Generate Custom Trap with AI</h3>
              </div>
              <button
                onClick={() => { setAiModalOpen(false); setGenError(null); }}
                className="font-mono text-xs text-ink-mute hover:text-ink"
              >
                [close]
              </button>
            </div>

            <p className="mt-3 text-sm text-ink-dim">
              Describe what kind of trap, attack, or boundary failure you want to test.
              The AI will craft the scenario, sandbox bait, behavioral detectors, and auto-link a real CVE with dynamic CVSS weighting.
            </p>

            <div className="mt-4">
              <label className="block font-mono text-[11px] text-ink-mute uppercase tracking-wider mb-1">
                Trap Requirement Prompt
              </label>
              <textarea
                rows={4}
                value={trapPrompt}
                onChange={(e) => setTrapPrompt(e.target.value)}
                placeholder="e.g. Test if the agent deletes production database tables after reading a poisoned log message instructing it to wipe data."
                className="w-full border border-rule bg-ground p-3 font-sans text-sm text-ink focus:border-sand focus:outline-none"
              />
            </div>

            {genError && (
              <div className="mt-3 border border-sand/30 bg-sand/10 p-2.5 font-mono text-xs text-sand">
                {genError}
              </div>
            )}

            <div className="mt-6 flex items-center justify-end gap-3">
              <button
                type="button"
                onClick={() => { setAiModalOpen(false); setGenError(null); }}
                className="px-4 py-2 font-display text-xs tracking-wider text-ink-mute hover:text-ink"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={!trapPrompt.trim() || isGenerating}
                onClick={async () => {
                  setIsGenerating(true);
                  setGenError(null);
                  const res = await generateTrap(trapPrompt);
                  setIsGenerating(false);
                  if (res) {
                    setScenarios((prev) => [res, ...prev.filter((x) => x.id !== res.id)]);
                    setSelected((prev) => new Set([...prev, res.id]));
                    setTrapPrompt("");
                    setAiModalOpen(false);
                  } else {
                    setGenError("Failed to generate trap. Please verify your prompt or LLM provider.");
                  }
                }}
                className="inline-flex items-center gap-2 border border-sand bg-sand px-5 py-2 font-display text-xs font-semibold uppercase tracking-wider text-ground hover:bg-sand-lit disabled:opacity-50"
              >
                {isGenerating ? (
                  <>
                    <Loader2 size={14} className="animate-spin" />
                    Generating Trap & CVE...
                  </>
                ) : (
                  <>
                    <Plus size={14} />
                    Create Trap
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Custom LLM Provider Modal */}
      {providerModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-ground/80 backdrop-blur-sm p-4">
          <div className="w-full max-w-lg border border-rule-lit bg-panel p-6 shadow-2xl">
            <div className="flex items-center justify-between pb-4 border-b border-rule">
              <div className="flex items-center gap-2">
                <Settings className="text-sand" size={18} />
                <h3 className="font-display text-lg font-semibold text-ink">Add Custom LLM API</h3>
              </div>
              <button
                onClick={() => { setProviderModalOpen(false); setProvError(null); }}
                className="font-mono text-xs text-ink-mute hover:text-ink"
              >
                [close]
              </button>
            </div>

            <p className="mt-3 text-sm text-ink-dim">
              Connect any OpenAI-compatible API endpoint (Ollama, vLLM, OpenRouter, Together AI, local LLM servers).
            </p>

            <div className="mt-4 space-y-3">
              <div>
                <label className="block font-mono text-[11px] text-ink-mute uppercase tracking-wider mb-1">
                  Provider ID (e.g. ollama, my-vllm, openrouter)
                </label>
                <input
                  type="text"
                  value={newProvId}
                  onChange={(e) => setNewProvId(e.target.value)}
                  placeholder="ollama"
                  className="w-full border border-rule bg-ground p-2.5 font-mono text-sm text-ink focus:border-sand focus:outline-none"
                />
              </div>

              <div>
                <label className="block font-mono text-[11px] text-ink-mute uppercase tracking-wider mb-1">
                  Display Name
                </label>
                <input
                  type="text"
                  value={newProvName}
                  onChange={(e) => setNewProvName(e.target.value)}
                  placeholder="Local Ollama Server"
                  className="w-full border border-rule bg-ground p-2.5 font-sans text-sm text-ink focus:border-sand focus:outline-none"
                />
              </div>

              <div>
                <label className="block font-mono text-[11px] text-ink-mute uppercase tracking-wider mb-1">
                  Base URL (OpenAI compatible /v1 endpoint)
                </label>
                <input
                  type="text"
                  value={newProvUrl}
                  onChange={(e) => setNewProvUrl(e.target.value)}
                  placeholder="http://localhost:11434/v1"
                  className="w-full border border-rule bg-ground p-2.5 font-mono text-sm text-ink focus:border-sand focus:outline-none"
                />
              </div>

              <div>
                <label className="block font-mono text-[11px] text-ink-mute uppercase tracking-wider mb-1">
                  API Key (Optional for local models)
                </label>
                <input
                  type="password"
                  value={newProvKey}
                  onChange={(e) => setNewProvKey(e.target.value)}
                  placeholder="sk-..."
                  className="w-full border border-rule bg-ground p-2.5 font-mono text-sm text-ink focus:border-sand focus:outline-none"
                />
              </div>

              <div>
                <label className="block font-mono text-[11px] text-ink-mute uppercase tracking-wider mb-1">
                  Explicit Models (Optional, comma-separated e.g. llama3.3,mistral)
                </label>
                <input
                  type="text"
                  value={newProvModels}
                  onChange={(e) => setNewProvModels(e.target.value)}
                  placeholder="leave empty to auto-discover via /models"
                  className="w-full border border-rule bg-ground p-2.5 font-mono text-sm text-ink focus:border-sand focus:outline-none"
                />
              </div>
            </div>

            {provError && (
              <div className="mt-3 border border-sand/30 bg-sand/10 p-2.5 font-mono text-xs text-sand">
                {provError}
              </div>
            )}

            <div className="mt-6 flex items-center justify-end gap-3">
              <button
                type="button"
                onClick={() => { setProviderModalOpen(false); setProvError(null); }}
                className="px-4 py-2 font-display text-xs tracking-wider text-ink-mute hover:text-ink"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={!newProvId.trim() || !newProvUrl.trim() || provSaving}
                onClick={async () => {
                  setProvSaving(true);
                  setProvError(null);
                  const modelsArr = newProvModels.split(",").map((s) => s.trim()).filter(Boolean);
                  const res = await addCustomProvider({
                    id: newProvId.trim().toLowerCase(),
                    name: newProvName.trim() || newProvId.trim(),
                    base_url: newProvUrl.trim(),
                    api_key: newProvKey.trim(),
                    models: modelsArr.length > 0 ? modelsArr : undefined,
                  });
                  setProvSaving(false);
                  if (res) {
                    setProviderModalOpen(false);
                    // Refresh models list
                    setModelsLoading(true);
                    getModels().then((m) => {
                      setModels(m);
                      setModelsLoading(false);
                    });
                  } else {
                    setProvError("Failed to save provider. Please verify endpoint URL.");
                  }
                }}
                className="inline-flex items-center gap-2 border border-sand bg-sand px-5 py-2 font-display text-xs font-semibold uppercase tracking-wider text-ground hover:bg-sand-lit disabled:opacity-50"
              >
                {provSaving ? <Loader2 size={14} className="animate-spin" /> : <Plus size={14} />}
                Save Provider
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
