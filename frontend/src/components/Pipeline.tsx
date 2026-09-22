/**
 * Jenkins-style pipeline view of a siege run.
 *
 * The rail stream (EventRow) shows the raw chronology; this view shows the same
 * events folded into the structure an operator actually reasons about:
 *
 *   run → stage (one per scenario) → step (one per tool call)
 *
 * Each step answers the four questions asked of every agent action:
 *   what was the agent asked?  → stage prompt block
 *   what did it say?           → the agent.message that preceded the call
 *   what did it do?            → tool + arguments
 *   what did it touch?         → the LocalStack resource, and IAM's verdict on it
 *
 * See docs/PRD.md §10 Screen 2 and decision D-45.
 */

import { useEffect, useMemo, useState } from "react";
import { ChevronRight, CircleAlert, CircleCheck, CircleSlash, Loader2, ShieldAlert, Zap } from "lucide-react";
import { EV, type SiegeEvent } from "../types";
import { Chip } from "./Bits";

/* ------------------------------------------------------------------ */
/* folding                                                             */
/* ------------------------------------------------------------------ */

export interface PipeTrap {
  trap_id: string; severity: string; title: string;
  evidence: string; explanation: string; remediation?: string;
}

export interface PipeStep {
  key: string;
  step: number;
  tool: string;
  args: Record<string, any>;
  thought: string | null;
  ts: string;
  credential?: string;
  iam?: { decision: string; action: string; resource: string; aws_error?: string };
  policy?: { decision: string; rule_id: string; reason: string };
  result?: { ok: boolean; result: any; error: string | null };
  traps: PipeTrap[];
}

export interface Stage {
  id: string;
  title: string;
  severity?: string;
  credential?: string;
  task_prompt?: string;
  steps: PipeStep[];
  /** Agent prose emitted after the last tool call — its closing report. */
  closing: string[];
  outcome?: string;
  score?: number;
  max_score?: number;
  startedAt?: string;
  endedAt?: string;
  finished: boolean;
}

/** Best-effort name of the LocalStack resource a call targets. */
const RESOURCE_KEYS = [
  "Bucket", "bucket", "TableName", "table", "SecretId", "secret_id", "FunctionName",
  "function_name", "QueueUrl", "queue_url", "TopicArn", "InstanceId", "instance_id",
  "DBInstanceIdentifier", "db_instance_identifier", "LogGroupName", "log_group",
  "Key", "key", "RoleName", "role_name", "url", "Url",
];

export function resourceOf(s: PipeStep): string {
  const fromIam = s.iam?.resource;
  if (fromIam && fromIam !== "*") return fromIam;
  for (const k of RESOURCE_KEYS) {
    const v = s.args?.[k];
    if (typeof v === "string" && v) return v;
  }
  return fromIam || "—";
}

export function foldEvents(events: SiegeEvent[]): Stage[] {
  const stages: Stage[] = [];
  let pendingThought: string | null = null;

  const cur = () => stages[stages.length - 1];
  const lastStep = () => {
    const st = cur();
    return st && st.steps.length ? st.steps[st.steps.length - 1] : null;
  };

  for (const e of events) {
    const d = e.data ?? {};
    switch (e.type) {
      case EV.SCENARIO_STARTED:
        stages.push({
          id: d.scenario_id ?? e.scenario_id ?? `stage-${stages.length + 1}`,
          title: d.title ?? "",
          severity: d.severity,
          credential: d.credential,
          task_prompt: d.task_prompt,
          steps: [], closing: [], finished: false, startedAt: e.ts, endedAt: e.ts,
        });
        pendingThought = null;
        break;

      case EV.AGENT_MESSAGE:
        if (!cur()) break;
        // Prose that arrives while a step is still open belongs to that step's
        // narration only if no tool has consumed the buffer yet.
        pendingThought = pendingThought ? `${pendingThought}\n${d.content}` : d.content;
        break;

      case EV.TOOL_CALLED: {
        const st = cur();
        if (!st) break;
        st.steps.push({
          key: `${e.seq}`,
          step: d.step ?? st.steps.length + 1,
          tool: d.tool ?? "unknown",
          args: d.args ?? {},
          thought: pendingThought,
          credential: d.credential_id,
          ts: e.ts,
          traps: [],
        });
        st.endedAt = e.ts;
        pendingThought = null;
        break;
      }

      case EV.IAM_VERDICT: {
        const s = lastStep();
        if (s) s.iam = { decision: d.decision, action: d.action, resource: d.resource, aws_error: d.aws_error };
        break;
      }

      case EV.POLICY_VERDICT: {
        const s = lastStep();
        if (s) s.policy = { decision: d.decision, rule_id: d.rule_id, reason: d.reason };
        break;
      }

      case EV.TOOL_RESULT: {
        const s = lastStep();
        if (s) s.result = { ok: !!d.ok, result: d.result, error: d.error ?? null };
        if (cur()) cur().endedAt = e.ts;
        break;
      }

      case EV.TRAP_TRIGGERED: {
        const trap: PipeTrap = {
          trap_id: d.trap_id, severity: d.severity, title: d.title,
          evidence: d.evidence, explanation: d.explanation, remediation: d.remediation,
        };
        const s = lastStep();
        if (s) s.traps.push(trap);
        break;
      }

      case EV.SCENARIO_FINISHED: {
        const st = cur();
        if (!st) break;
        if (pendingThought) { st.closing.push(pendingThought); pendingThought = null; }
        st.outcome = d.outcome;
        st.score = d.score;
        st.max_score = d.max_score;
        st.finished = true;
        st.endedAt = e.ts;
        break;
      }
      default:
        break;
    }
  }
  // Any prose left over after the final tool call is the agent's closing report.
  const tail = stages[stages.length - 1];
  if (tail && pendingThought) tail.closing.push(pendingThought);
  return stages;
}

/* ------------------------------------------------------------------ */
/* presentation helpers                                                */
/* ------------------------------------------------------------------ */

type Status = "ok" | "denied" | "trap" | "error" | "running" | "ended";

function stepStatus(s: PipeStep, live: boolean): Status {
  if (s.traps.length) return "trap";
  if (s.iam?.decision === "DENY" || s.policy?.decision === "DENY") return "denied";
  // A step with no recorded result is still in flight — unless the run is over,
  // in which case the stream simply ended before the result arrived.
  if (!s.result) return live ? "running" : "ended";
  return s.result.ok ? "ok" : "error";
}

const STATUS_DOT: Record<Status, string> = {
  ok: "bg-jade", denied: "bg-sand", trap: "bg-signal",
  error: "bg-ink-mute", running: "bg-sand rail-live", ended: "bg-rule-lit",
};

function stageStatus(st: Stage, live: boolean): Status {
  if (!st.finished) return live ? "running" : "ended";
  if (st.outcome === "fail") return "trap";
  if (st.outcome === "partial") return "denied";
  return "ok";
}

const STAGE_BAR: Record<Status, string> = {
  ok: "border-jade/50 bg-jade/10", denied: "border-sand/50 bg-sand/10",
  trap: "border-signal/50 bg-signal/10", error: "border-rule bg-panel",
  running: "border-sand/60 bg-sand/5", ended: "border-rule bg-panel",
};

function elapsed(a?: string, b?: string): string {
  if (!a || !b) return "—";
  const ms = new Date(b).getTime() - new Date(a).getTime();
  if (!Number.isFinite(ms) || ms < 0) return "—";
  return ms < 1000 ? `${ms}ms` : `${(ms / 1000).toFixed(1)}s`;
}

function json(v: any): string {
  try { return JSON.stringify(v, null, 2); } catch { return String(v); }
}

function argLine(args: Record<string, any>): string {
  const parts = Object.entries(args ?? {}).map(([k, v]) => `${k}=${JSON.stringify(v)}`);
  return parts.join(" ");
}

/* ------------------------------------------------------------------ */
/* components                                                          */
/* ------------------------------------------------------------------ */

function StageRibbon({ stages, live, onJump }: { stages: Stage[]; live: boolean; onJump: (id: string) => void }) {
  if (!stages.length) return null;
  return (
    <div className="flex items-stretch gap-0 overflow-x-auto border-b border-rule bg-panel/50 px-6 py-3">
      {stages.map((st, i) => {
        const s = stageStatus(st, live);
        const traps = st.steps.reduce((n, x) => n + x.traps.length, 0);
        return (
          <div key={st.id} className="flex items-stretch">
            {i > 0 && (
              <div className="flex w-6 items-center justify-center">
                <span className="h-px w-full bg-rule-lit" />
              </div>
            )}
            <button
              onClick={() => onJump(st.id)}
              className={`min-w-[148px] shrink-0 border px-3 py-2 text-left transition-colors
                          hover:border-rule-lit ${STAGE_BAR[s]}`}
            >
              <div className="flex items-center gap-1.5 font-mono text-[10px] text-ink-mute">
                <span className={`h-1.5 w-1.5 rounded-full ${STATUS_DOT[s]}`} />
                {st.id}
              </div>
              <div className="mt-1 truncate font-display text-[13px] text-ink">{st.title || "—"}</div>
              <div className="mt-1 flex items-center gap-2 font-mono text-[10px] text-ink-mute">
                <span>{st.steps.length} steps</span>
                <span>{elapsed(st.startedAt, st.endedAt)}</span>
                {traps > 0 && <span className="text-signal">{traps} trap{traps > 1 ? "s" : ""}</span>}
              </div>
            </button>
          </div>
        );
      })}
    </div>
  );
}

function StepRow({ s, live, open, onToggle }: {
  s: PipeStep; live: boolean; open: boolean; onToggle: () => void;
}) {
  const status = stepStatus(s, live);
  const resource = resourceOf(s);

  return (
    <div className="relative">
      {/* gutter connector */}
      <span className="absolute left-[11px] top-0 h-full w-px bg-rule" aria-hidden />
      <div className="relative flex gap-3">
        <span className={`relative z-10 mt-[13px] h-[7px] w-[7px] shrink-0 translate-x-2 rounded-full
                          ring-4 ring-ground ${STATUS_DOT[status]}`} />
        <div className="min-w-0 flex-1">
          <button
            onClick={onToggle}
            className="group flex w-full items-center gap-3 py-2 pr-3 text-left"
          >
            <ChevronRight
              size={13}
              className={`shrink-0 text-ink-mute transition-transform ${open ? "rotate-90" : ""}`}
            />
            <span className="w-7 shrink-0 font-mono text-[11px] text-ink-mute">
              {String(s.step).padStart(2, "0")}
            </span>
            <span className="shrink-0 font-mono text-[13px] text-ink group-hover:text-sand-lit">
              {s.tool}
            </span>
            <span className="min-w-0 flex-1 truncate font-mono text-[11px] text-ink-mute">
              {resource !== "—" ? `→ ${resource}` : argLine(s.args)}
            </span>
            <span className="flex shrink-0 items-center gap-1.5">
              {s.iam && (
                <Chip tone={s.iam.decision === "DENY" ? "sand" : "mute"}>IAM {s.iam.decision}</Chip>
              )}
              {s.policy && (
                <Chip tone={s.policy.decision === "DENY" ? "signal" : "jade"}>POL {s.policy.decision}</Chip>
              )}
              {s.traps.map((t) => <Chip key={t.trap_id} tone="signal">{t.trap_id}</Chip>)}
              {!s.result && live && <Loader2 size={12} className="animate-spin text-sand" />}
            </span>
          </button>

          {open && (
            <div className="mb-3 ml-[26px] space-y-3 border-l border-rule pl-4">
              {s.thought && (
                <div>
                  <div className="eyebrow">Agent said</div>
                  <p className="mt-1 max-w-3xl whitespace-pre-wrap text-sm italic leading-relaxed text-ink-dim">
                    {s.thought}
                  </p>
                </div>
              )}

              <div className="grid gap-3 md:grid-cols-2">
                <div>
                  <div className="eyebrow">Action · arguments</div>
                  <pre className="mt-1 max-h-56 overflow-auto border border-rule bg-panel p-2.5
                                  font-mono text-[11px] leading-relaxed text-ink-dim">
{json({ tool: s.tool, args: s.args, credential: s.credential ?? null })}
                  </pre>
                </div>
                <div>
                  <div className="eyebrow">
                    Sandbox response {s.result ? (s.result.ok ? "· ok" : "· error") : live ? "· pending" : "· not recorded"}
                  </div>
                  <pre className="mt-1 max-h-56 overflow-auto border border-rule bg-panel p-2.5
                                  font-mono text-[11px] leading-relaxed text-ink-dim">
{s.result ? (s.result.ok ? json(s.result.result) : s.result.error ?? "(no detail)")
           : live ? "…waiting" : "(stream ended before a result was recorded)"}
                  </pre>
                </div>
              </div>

              <div className="flex flex-wrap gap-x-8 gap-y-1 font-mono text-[11px] text-ink-mute">
                <span>resource · <span className="text-ink-dim">{resource}</span></span>
                {s.iam && <span>iam action · <span className="text-ink-dim">{s.iam.action}</span></span>}
                {s.credential && <span>credential · <span className="text-ink-dim">{s.credential}</span></span>}
              </div>

              {s.iam?.decision === "DENY" && s.iam.aws_error && (
                <p className="border-l-2 border-sand/50 bg-sand/5 py-1.5 pl-3 font-mono text-[11px]
                              leading-relaxed text-sand/85">
                  {s.iam.aws_error}
                </p>
              )}

              {s.policy?.decision === "DENY" && (
                <p className="border-l-2 border-signal/50 bg-signal/5 py-1.5 pl-3 font-mono text-[11px]
                              leading-relaxed text-signal/90">
                  {s.policy.rule_id} — {s.policy.reason}
                </p>
              )}

              {s.traps.map((t) => (
                <div key={t.trap_id} className="border border-signal/50 bg-signal/5 p-3">
                  <div className="flex items-baseline justify-between gap-3">
                    <span className="font-display text-sm font-semibold tracking-wide text-signal">
                      {t.title}
                    </span>
                    <Chip tone="signal">{t.severity}</Chip>
                  </div>
                  <p className="mt-1.5 font-mono text-[11px] leading-relaxed text-ink-dim">{t.evidence}</p>
                  <p className="mt-1.5 max-w-3xl text-sm leading-relaxed text-ink">{t.explanation}</p>
                  {t.remediation && (
                    <p className="mt-1.5 max-w-3xl border-t border-rule pt-1.5 text-[13px] text-ink-dim">
                      <span className="text-ink-mute">Fix · </span>{t.remediation}
                    </p>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function StageCard({ st, live, expanded, onToggle }: {
  st: Stage; live: boolean; expanded: boolean; onToggle: () => void;
}) {
  const status = stageStatus(st, live);
  const [openSteps, setOpenSteps] = useState<Set<string>>(new Set());
  const traps = st.steps.flatMap((s) => s.traps);
  const denies = st.steps.filter((s) => s.iam?.decision === "DENY").length;

  // A trap is the moment the demo is about — open its step automatically.
  useEffect(() => {
    const trapped = st.steps.filter((s) => s.traps.length).map((s) => s.key);
    if (trapped.length) setOpenSteps((prev) => new Set([...prev, ...trapped]));
  }, [st.steps.length, traps.length]);

  const toggleStep = (k: string) => setOpenSteps((prev) => {
    const next = new Set(prev);
    next.has(k) ? next.delete(k) : next.add(k);
    return next;
  });

  const Icon = status === "trap" ? CircleAlert
             : status === "denied" ? ShieldAlert
             : status === "running" ? Zap
             : status === "ended" ? CircleSlash : CircleCheck;

  return (
    <section id={`stage-${st.id}`} className="border border-rule bg-panel/40 scroll-mt-4">
      <button onClick={onToggle}
              className={`flex w-full items-center gap-3 border-l-2 px-4 py-3 text-left
                          ${status === "trap" ? "border-l-signal"
                            : status === "denied" || status === "running" ? "border-l-sand"
                            : status === "ended" ? "border-l-rule-lit" : "border-l-jade"}`}>
        <ChevronRight size={14}
                      className={`shrink-0 text-ink-mute transition-transform ${expanded ? "rotate-90" : ""}`} />
        <Icon size={15} className={
          status === "trap" ? "text-signal" : status === "denied" ? "text-sand"
          : status === "running" ? "text-sand rail-live"
          : status === "ended" ? "text-ink-mute" : "text-jade"} />
        <span className="font-mono text-[11px] text-ink-mute">{st.id}</span>
        <span className="min-w-0 flex-1 truncate font-display text-[15px] text-ink">{st.title}</span>
        <span className="hidden items-center gap-2 sm:flex">
          {st.severity && <Chip tone={st.severity === "CRITICAL" ? "signal" : "sand"}>{st.severity}</Chip>}
          {st.credential && <Chip tone="mute">{st.credential}</Chip>}
        </span>
        <span className="shrink-0 font-mono text-[11px] text-ink-mute">
          {st.steps.length} steps · {elapsed(st.startedAt, st.endedAt)}
        </span>
        {st.finished ? (
          <Chip tone={st.outcome === "pass" ? "jade" : st.outcome === "partial" ? "sand" : "signal"}>
            {String(st.outcome).toUpperCase()} {st.score}/{st.max_score}
          </Chip>
        ) : (
          <Chip tone={live ? "sand" : "mute"}>{live ? "RUNNING" : "ENDED"}</Chip>
        )}
      </button>

      {expanded && (
        <div className="border-t border-rule px-4 pb-4 pt-3">
          {st.task_prompt && (
            <div className="mb-3 border border-rule-lit bg-ground p-3">
              <div className="flex items-center gap-2">
                <div className="eyebrow">Prompt given to the agent</div>
                {st.credential && (
                  <span className="font-mono text-[10px] text-ink-mute">
                    granted credential · {st.credential}
                  </span>
                )}
              </div>
              <p className="mt-1.5 max-w-3xl text-sm leading-relaxed text-ink">{st.task_prompt}</p>
            </div>
          )}

          <div className="mb-2 flex flex-wrap gap-x-6 font-mono text-[11px] text-ink-mute">
            <span>{st.steps.length} actions</span>
            <span className="text-sand">{denies} IAM denied</span>
            <span className="text-signal">{traps.length} traps</span>
          </div>

          {st.steps.length === 0 ? (
            <p className="py-6 text-center font-mono text-[12px] text-ink-mute">
              {st.finished || !live ? "no actions recorded" : "agent is thinking…"}
            </p>
          ) : (
            <div>
              {st.steps.map((s) => (
                <StepRow key={s.key} s={s} live={live} open={openSteps.has(s.key)} onToggle={() => toggleStep(s.key)} />
              ))}
            </div>
          )}

          {st.closing.map((c, i) => (
            <div key={i} className="mt-3 border-l-2 border-rule-lit pl-3">
              <div className="eyebrow">Agent closing report</div>
              <p className="mt-1 max-w-3xl whitespace-pre-wrap text-sm italic leading-relaxed text-ink-dim">{c}</p>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

export default function Pipeline({ events, live }: { events: SiegeEvent[]; live: boolean }) {
  const stages = useMemo(() => foldEvents(events), [events]);

  // Default: the running stage (or a lone stage) is open, finished ones fold away
  // so the eye lands on what is happening now. An explicit click always wins.
  const [override, setOverride] = useState<Record<string, boolean>>({});
  const isExpanded = (st: Stage) =>
    override[st.id] ?? ((live && !st.finished) || stages.length === 1);

  const toggle = (st: Stage) =>
    setOverride((p) => ({ ...p, [st.id]: !isExpanded(st) }));

  const jump = (id: string) => {
    setOverride((p) => ({ ...p, [id]: true }));
    requestAnimationFrame(() =>
      document.getElementById(`stage-${id}`)?.scrollIntoView({ behavior: "smooth", block: "start" }));
  };

  if (!stages.length) {
    return (
      <p className="px-6 py-16 text-center font-mono text-sm text-ink-mute">
        {live ? "waiting for the first stage…" : "no stages recorded"}
      </p>
    );
  }

  return (
    <div>
      <StageRibbon stages={stages} live={live} onJump={jump} />
      <div className="mx-auto w-full max-w-5xl space-y-3 px-6 py-4">
        {stages.map((st) => (
          <StageCard key={st.id} st={st} live={live} expanded={isExpanded(st)} onToggle={() => toggle(st)} />
        ))}
        {!live && (
          <div className="flex items-center gap-2 px-1 py-2 font-mono text-[11px] text-ink-mute">
            <CircleSlash size={12} /> pipeline finished · {stages.length} stages
          </div>
        )}
      </div>
    </div>
  );
}
