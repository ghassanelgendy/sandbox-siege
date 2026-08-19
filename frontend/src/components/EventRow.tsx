/**
 * The signature element: every event is rendered between two rails.
 *
 *   left rail  = L1, permission (IAM)      -- flares sand on DENY
 *   right rail = L2, judgement (detectors) -- flares signal on a trap
 *
 * The story the audience watches is the handoff: the left rail flares amber
 * while the boundary holds, then goes quiet the moment the agent escalates --
 * and the right rail lights red. Permission stopped protecting you.
 */

import { EV, type SiegeEvent } from "../types";
import { Chip } from "./Bits";

function railClasses(e: SiegeEvent): [string, string] {
  switch (e.type) {
    case EV.IAM_VERDICT:
      return [e.data.decision === "DENY" ? "rail-l1-deny" : "rail-l1-allow", ""];
    case EV.TRAP_TRIGGERED:
      return ["", "rail-l2-trap"];
    case EV.POLICY_VERDICT:
      return ["", e.data.decision === "DENY" ? "rail-l2-trap" : "rail-l2-ok"];
    default:
      return ["", ""];
  }
}

function Body({ e }: { e: SiegeEvent }) {
  const d = e.data;
  switch (e.type) {
    case EV.SCENARIO_STARTED:
      return (
        <div className="border-l-2 border-ink-dim/40 pl-3">
          <div className="eyebrow">{d.scenario_id} · granted {d.credential}</div>
          <p className="font-display text-lg text-ink">{d.title}</p>
          <p className="mt-1 max-w-2xl text-sm text-ink-dim">{d.task_prompt}</p>
        </div>
      );

    case EV.AGENT_MESSAGE:
      return <p className="max-w-3xl text-sm italic leading-relaxed text-ink-dim">{d.content}</p>;

    case EV.TOOL_CALLED: {
      const args = Object.entries(d.args ?? {})
        .map(([k, v]) => `${k}=${JSON.stringify(v)}`).join(" ");
      return (
        <div className="font-mono text-[13px]">
          <span className="text-ink-mute">{String(d.step).padStart(2, "0")}</span>{" "}
          <span className="text-ink">{d.tool}</span>{" "}
          <span className="text-ink-mute">{args}</span>
        </div>
      );
    }

    case EV.IAM_VERDICT: {
      const deny = d.decision === "DENY";
      return (
        <div className="font-mono text-[12px]">
          <Chip tone={deny ? "sand" : "mute"}>IAM {d.decision}</Chip>{" "}
          <span className="text-ink-mute">{d.action}</span>
          {deny && d.aws_error && (
            <p className="mt-1 max-w-3xl border-l border-sand/40 pl-2 text-[11px] leading-relaxed text-sand/85">
              {d.aws_error}
            </p>
          )}
        </div>
      );
    }

    case EV.POLICY_VERDICT:
      return (
        <div className="font-mono text-[12px]">
          <Chip tone={d.decision === "DENY" ? "signal" : "jade"}>POLICY {d.decision}</Chip>{" "}
          <span className="text-ink-mute">{d.reason}</span>
        </div>
      );

    case EV.TOOL_RESULT:
      return d.ok ? null : (
        <div className="font-mono text-[12px] text-ink-mute">↳ {d.error}</div>
      );

    case EV.TRAP_TRIGGERED:
      return (
        <div className="trap-flare border border-signal/50 p-4">
          <div className="flex items-baseline justify-between gap-3">
            <span className="font-display text-base font-semibold tracking-wide text-signal">
              {d.title}
            </span>
            <Chip tone="signal">{d.trap_id}</Chip>
          </div>
          <p className="mt-2 font-mono text-[11px] leading-relaxed text-ink-dim">{d.evidence}</p>
          <p className="mt-2 max-w-3xl text-sm leading-relaxed text-ink">{d.explanation}</p>
        </div>
      );

    case EV.SCENARIO_FINISHED: {
      const tone = d.outcome === "pass" ? "jade" : d.outcome === "partial" ? "sand" : "signal";
      return (
        <div className="flex items-center gap-2 border-t border-rule pt-3 font-mono text-[12px]">
          <Chip tone={tone as "jade"}>{String(d.outcome).toUpperCase()}</Chip>
          <span className="text-ink-mute">{d.scenario_id} scored {d.score}/{d.max_score}</span>
        </div>
      );
    }

    case EV.RUN_FINISHED:
      return (
        <div className="border border-rule-lit bg-panel-2 p-4">
          <div className="eyebrow">Siege complete</div>
          <p className="mt-1 font-display text-2xl text-ink">
            Trust score {d.trust_score} · grade {d.grade} · gate {d.gate}
          </p>
          <p className="mt-1 text-sm text-ink-dim">{d.summary}</p>
        </div>
      );

    case EV.RUN_ERROR:
      return <p className="font-mono text-[12px] text-signal">error: {d.message}</p>;

    default:
      return null;
  }
}

export default function EventRow({ e }: { e: SiegeEvent }) {
  const [l1, l2] = railClasses(e);
  const body = <Body e={e} />;
  if (!body) return null;

  return (
    <div className="grid grid-cols-[3px_1fr_3px]">
      <div className={`rail ${l1}`} />
      <div className="px-5 py-2">{body}</div>
      <div className={`rail ${l2}`} />
    </div>
  );
}
