import { useEffect, useMemo, useRef, useState } from "react";
import { GitBranch, List } from "lucide-react";
import { EV, type Report, type SiegeEvent } from "../types";
import { getReport, stopRun, streamFixture, streamRun } from "../api";
import EventRow from "../components/EventRow";
import Pipeline, { foldEvents } from "../components/Pipeline";
import { Chip, Eyebrow } from "../components/Bits";

interface Props {
  runId: string | null;
  demo: boolean;
  /** shown as a banner when a live launch fell back to the sample stream */
  notice?: string | null;
  onFinished: (report: Report | null) => void;
  report: Report | null;
  onViewReport: () => void;
}

type ViewMode = "pipeline" | "stream";

export default function Console({ runId, demo, notice, onFinished, report, onViewReport }: Props) {
  const [events, setEvents] = useState<SiegeEvent[]>([]);
  const [live, setLive] = useState(true);
  const [pinned, setPinned] = useState(true);
  const [mode, setMode] = useState<ViewMode>("pipeline");
  const endRef = useRef<HTMLDivElement>(null);
  const boxRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setEvents([]); setLive(true);
    const push = (e: SiegeEvent) => setEvents((prev) => [...prev, e]);
    const done = async () => {
      setLive(false);
      onFinished(runId && !demo ? await getReport(runId) : null);
    };
    return demo || !runId ? streamFixture(push, done) : streamRun(runId, push, done);
  }, [runId, demo]);

  useEffect(() => {
    if (pinned) endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [events, pinned]);

  const onScroll = () => {
    const el = boxRef.current;
    if (!el) return;
    setPinned(el.scrollHeight - el.scrollTop - el.clientHeight < 80);
  };

  const runStarted = events.find((e) => e.type === EV.RUN_STARTED);
  const traps = events.filter((e) => e.type === EV.TRAP_TRIGGERED);
  const denies = events.filter((e) => e.type === EV.IAM_VERDICT && e.data.decision === "DENY");
  const current = [...events].reverse().find((e) => e.type === EV.SCENARIO_STARTED);
  const finished = events.filter((e) => e.type === EV.SCENARIO_FINISHED);
  const stages = useMemo(() => foldEvents(events), [events]);
  const actions = stages.reduce((n, s) => n + s.steps.length, 0);

  return (
    <div className="flex h-[calc(100vh-3.5rem)]">
      {/* left: what the two rails mean, and where we are */}
      <aside className="hidden w-72 shrink-0 overflow-y-auto border-r border-rule p-6 lg:block">
        <Eyebrow>Reading the rails</Eyebrow>
        <dl className="mt-3 space-y-4 text-sm">
          <div className="flex gap-3">
            <span className="mt-1 h-8 w-0.5 shrink-0 bg-sand" />
            <div>
              <dt className="font-display text-ink">Left · permission</dt>
              <dd className="text-ink-mute">IAM decided. Amber means it refused.</dd>
            </div>
          </div>
          <div className="flex gap-3">
            <span className="mt-1 h-8 w-0.5 shrink-0 bg-signal" />
            <div>
              <dt className="font-display text-ink">Right · judgement</dt>
              <dd className="text-ink-mute">A trap fired. Permission allowed it.</dd>
            </div>
          </div>
        </dl>

        <div className="mt-8 border-t border-rule pt-6">
          <Eyebrow>Scenarios</Eyebrow>
          <ul className="mt-3 space-y-2">
            {finished.map((e) => (
              <li key={e.seq} className="flex items-center justify-between font-mono text-[11px]">
                <span className="text-ink-mute">{e.data.scenario_id}</span>
                <Chip tone={e.data.outcome === "pass" ? "jade"
                          : e.data.outcome === "partial" ? "sand" : "signal"}>
                  {String(e.data.outcome).toUpperCase()}
                </Chip>
              </li>
            ))}
            {current && !finished.some((f) => f.data.scenario_id === current.data.scenario_id) && (
              <li className="flex items-center justify-between font-mono text-[11px]">
                <span className="text-ink">{current.data.scenario_id}</span>
                {live
                  ? <span className="text-sand rail-live">running</span>
                  : <span className="text-ink-mute">ended</span>}
              </li>
            )}
          </ul>
        </div>
      </aside>

      {/* centre: the console */}
      <div className="flex min-w-0 flex-1 flex-col">
        {notice && (
          <div role="alert"
               className="border-b border-sand/40 bg-sand/10 px-6 py-2 font-mono text-[12px] text-sand">
            {notice}
          </div>
        )}
        <header className="flex flex-wrap items-center justify-between gap-3 border-b border-rule px-6 py-3">
          <div className="flex items-center gap-3">
            <span className={`h-2 w-2 rounded-full ${live ? "bg-sand rail-live" : "bg-ink-mute"}`} />
            <span className="font-display text-sm tracking-wide text-ink">
              {live ? "Siege in progress" : "Siege complete"}
            </span>
            {runStarted?.data.model && (
              <Chip tone="sand">
                {runStarted.data.model} · {runStarted.data.agent_framework || "raw_llm"}
              </Chip>
            )}
            {demo && <Chip tone="sand">sample data · not a live run</Chip>}
            {live && !demo && runId && (
              <button
                onClick={() => stopRun(runId)}
                className="ml-2 border border-signal/40 bg-signal/10 px-2.5 py-0.5 font-mono text-[11px] font-semibold text-signal hover:bg-signal/20 transition-colors"
              >
                Stop Test
              </button>
            )}
          </div>
          <div className="flex items-center gap-5 font-mono text-[11px] text-ink-mute">
            <span>{stages.length} stages</span>
            <span>{actions} actions</span>
            <span className="text-sand">{denies.length} IAM denied</span>
            <span className="text-signal">
              {traps.length} {traps.length === 1 ? "trap" : "traps"}
            </span>
            {/* view switch — pipeline is the operator's read, the rail stream the raw chronology */}
            <div className="flex border border-rule">
              {([["pipeline", "Pipeline", GitBranch], ["stream", "Stream", List]] as const).map(
                ([id, label, Icon]) => (
                  <button key={id} onClick={() => setMode(id)}
                          className={`inline-flex items-center gap-1.5 px-2.5 py-1 transition-colors
                            ${mode === id ? "bg-sand/15 text-sand" : "text-ink-mute hover:text-ink"}`}>
                    <Icon size={11} /> {label}
                  </button>
                ))}
            </div>
          </div>
        </header>

        <div ref={boxRef} onScroll={onScroll} className="console flex-1 overflow-y-auto">
          {mode === "pipeline" ? (
            <Pipeline events={events} live={live} />
          ) : (
            /* The rails only read as a pair when they bracket a column the eye can
               span in one go. Left unconstrained they drift to the screen edges. */
            <div className="mx-auto w-full max-w-4xl py-4">
              {events.length === 0 && (
                <p className="px-6 py-16 text-center font-mono text-sm text-ink-mute">
                  waiting for the first action…
                </p>
              )}
              {events.map((e) => <EventRow key={`${e.seq}-${e.type}`} e={e} />)}
            </div>
          )}
          <div ref={endRef} />
        </div>

        {!pinned && live && (
          <button onClick={() => setPinned(true)}
                  className="border-t border-rule bg-panel py-2 font-mono text-[11px] text-ink-mute
                             hover:text-ink">
            jump to latest ↓
          </button>
        )}

        {!live && report && (
          <div className="flex items-center justify-between gap-4 border-t border-rule bg-panel px-6 py-4">
            <div>
              <div className="eyebrow">Siege complete</div>
              <p className="mt-0.5 font-display text-lg text-ink">
                Trust score {report.trust_score} · grade {report.grade} ·
                {" "}<span className={report.gate === "PASS" ? "text-jade" : "text-signal"}>
                  gate {report.gate}
                </span>
              </p>
            </div>
            <button onClick={onViewReport}
                    className="border border-sand bg-sand px-5 py-2.5 font-display
                               font-semibold tracking-wide text-ground">
              View report card →
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
