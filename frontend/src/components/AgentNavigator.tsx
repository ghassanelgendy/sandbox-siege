import { useState } from "react";
import { ExternalLink, X, Terminal, Cpu } from "lucide-react";
import type { AgentFramework } from "../api";
import { Eyebrow, Panel } from "./Bits";

interface Props {
  agents: AgentFramework[];
  isOpen: boolean;
  onClose: () => void;
  onSelectAgent: (id: string) => void;
}

export default function AgentNavigator({ agents, isOpen, onClose, onSelectAgent }: Props) {
  const [activeId, setActiveId] = useState<string>(agents[0]?.id || "raw_llm");

  if (!isOpen) return null;

  const active = agents.find((a) => a.id === activeId) || agents[0];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-ground/80 backdrop-blur-sm p-6">
      <div className="relative w-full max-w-4xl max-h-[85vh] flex flex-col border border-rule bg-panel shadow-2xl overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-rule px-6 py-4 bg-ground/50">
          <div className="flex items-center gap-3">
            <Cpu size={20} className="text-sand" />
            <div>
              <h2 className="font-display text-lg font-semibold text-ink">Agent Navigator & Framework Inspector</h2>
              <p className="text-xs text-ink-dim">Explore supported AI Agent Frameworks, tool capabilities, and open-source GitHub references.</p>
            </div>
          </div>
          <button onClick={onClose} className="p-1 text-ink-mute hover:text-ink">
            <X size={20} />
          </button>
        </div>

        {/* Content */}
        <div className="flex flex-1 min-h-0 divide-x divide-rule overflow-hidden">
          {/* Sidebar List */}
          <div className="w-64 shrink-0 overflow-y-auto bg-ground/30 divide-y divide-rule/50">
            {agents.map((a) => {
              const selected = a.id === activeId;
              return (
                <button
                  key={a.id}
                  onClick={() => setActiveId(a.id)}
                  className={`w-full p-4 text-left transition-colors flex flex-col gap-1 ${
                    selected ? "bg-sand/10 border-l-2 border-sand" : "hover:bg-panel"
                  }`}
                >
                  <span className="font-display text-sm font-semibold text-ink">{a.name}</span>
                  <span className="font-mono text-[10px] text-ink-mute truncate">{a.id}</span>
                </button>
              );
            })}
          </div>

          {/* Details Panel */}
          {active && (
            <div className="flex-1 p-6 overflow-y-auto space-y-6">
              <div className="flex items-start justify-between">
                <div>
                  <Eyebrow>{active.id}</Eyebrow>
                  <h3 className="font-display text-2xl font-semibold text-ink mt-1">{active.name}</h3>
                  <p className="text-sm text-ink-dim mt-2 leading-relaxed">{active.description}</p>
                </div>
                <div className="flex gap-2">
                  <a
                    href={active.github_url}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 border border-rule-lit font-mono text-xs text-ink-dim hover:text-ink hover:border-ink transition-colors"
                  >
                    GitHub <ExternalLink size={13} />
                  </a>
                  <button
                    onClick={() => {
                      onSelectAgent(active.id);
                      onClose();
                    }}
                    className="inline-flex items-center gap-1.5 px-4 py-1.5 border border-sand bg-sand font-mono text-xs font-semibold text-ground"
                  >
                    Select for Test
                  </button>
                </div>
              </div>

              {/* Assigned Tools */}
              <div>
                <div className="mb-2">
                  <Eyebrow>Assigned Tool Surface ({active.tools?.length || 0} Tools)</Eyebrow>
                </div>
                <div className="flex flex-wrap gap-2">
                  {active.tools?.map((t) => (
                    <span key={t} className="inline-flex items-center gap-1 px-2.5 py-1 border border-rule bg-ground font-mono text-xs text-ink">
                      <Terminal size={12} className="text-sand" /> {t}
                    </span>
                  ))}
                </div>
              </div>

              {/* System Prompt / Backstory */}
              <div>
                <div className="mb-2">
                  <Eyebrow>Agent System Persona & Prompt</Eyebrow>
                </div>
                <Panel className="p-4 bg-ground font-mono text-xs leading-relaxed text-ink-dim whitespace-pre-wrap">
                  {active.system_prompt}
                </Panel>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
