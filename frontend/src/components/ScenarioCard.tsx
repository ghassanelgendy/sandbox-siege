import { Dot, OUTCOME_COLOR, OUTCOME_LABEL } from "./Bits";
import type { Finding, ScenarioResult } from "../types";

export default function ScenarioCard({
  s, onFinding,
}: { s: ScenarioResult; onFinding: (f: Finding) => void }) {
  const real = s.findings.filter((f) => f.severity !== "INFO");
  const positives = s.findings.filter((f) => f.severity === "INFO");

  return (
    <div className="card-3d border border-rule bg-panel p-5">
      <div className="flex items-baseline justify-between gap-4">
        <div className="min-w-0">
          <div className="eyebrow">{s.id} · weight {s.weight}</div>
          <h3 className="mt-0.5 truncate font-display text-lg text-ink">{s.title}</h3>
        </div>
        <div className="shrink-0 text-right">
          <div className={`flex items-center justify-end gap-1.5 font-display text-sm font-semibold
                           tracking-wide ${OUTCOME_COLOR[s.outcome]}`}>
            <Dot outcome={s.outcome} />
            {OUTCOME_LABEL[s.outcome]}
          </div>
          <div className="font-mono text-[12px] text-ink-mute tabular-nums">
            {s.score}/{s.max_score}
          </div>
        </div>
      </div>

      {s.error && <p className="mt-3 font-mono text-[11px] text-signal">{s.error}</p>}

      {(real.length > 0 || positives.length > 0) && (
        <ul className="mt-4 space-y-1.5 border-t border-rule pt-3">
          {[...real, ...positives].map((f) => (
            <li key={f.trap_id}>
              <button onClick={() => onFinding(f)}
                      className="group flex w-full items-baseline gap-2 text-left">
                <span className={`font-mono text-[11px] ${f.severity === "INFO" ? "text-jade" : "text-signal"}`}>
                  {f.severity === "INFO" ? "✓" : "▲"}
                </span>
                <span className="flex-1 text-sm text-ink-dim group-hover:text-ink">{f.title}</span>
                <span className="font-mono text-[10px] text-ink-mute">step {f.step}</span>
              </button>
            </li>
          ))}
        </ul>
      )}

      <div className="mt-4 flex gap-4 font-mono text-[11px] text-ink-mute">
        <span>{s.steps_used} steps</span>
        <span>{s.duration_s}s</span>
      </div>
    </div>
  );
}
