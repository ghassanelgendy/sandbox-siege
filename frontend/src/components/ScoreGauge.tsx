/**
 * Trust score as a structural load readout, not a donut.
 * The threshold is a physical marker on the bar: you are either over the line
 * or you are not.
 */

import { GRADE_COLOR } from "./Bits";
import type { Grade, Gate } from "../types";

export default function ScoreGauge({
  score, grade, gate, threshold,
}: { score: number; grade: Grade; gate: Gate; threshold: number }) {
  const pct = Math.max(0, Math.min(100, score));
  const fill = gate === "PASS" ? "bg-jade" : score >= threshold * 0.6 ? "bg-sand" : "bg-signal";

  return (
    <div>
      <div className="flex items-end justify-between gap-6">
        <div>
          <div className="eyebrow">Trust score</div>
          <div className="flex items-baseline gap-3">
            <span className="font-display text-7xl leading-none font-semibold tabular-nums text-ink">
              {score % 1 === 0 ? score : score.toFixed(1)}
            </span>
            <span className="font-display text-2xl text-ink-mute">/100</span>
          </div>
        </div>
        <div className="text-right">
          <div className="eyebrow">Grade</div>
          <div className={`font-display text-7xl leading-none font-semibold ${GRADE_COLOR[grade]}`}>
            {grade}
          </div>
        </div>
      </div>

      <div className="relative mt-6 h-3 w-full border border-rule bg-ground">
        <div className={`h-full ${fill} transition-[width] duration-700 ease-out`}
             style={{ width: `${pct}%` }} />
        <div className="absolute inset-y-[-6px] w-px bg-ink-dim"
             style={{ left: `${threshold}%` }} aria-hidden />
      </div>

      <div className="mt-2 flex justify-between font-mono text-[11px] text-ink-mute">
        <span>0</span>
        <span style={{ marginLeft: `${threshold - 8}%` }}>threshold {threshold}</span>
        <span>100</span>
      </div>

      <div className="mt-5 flex items-center gap-3">
        <span className={`border px-3 py-1 font-display text-sm font-semibold tracking-widest
                          ${gate === "PASS"
                            ? "border-jade/50 bg-jade/10 text-jade"
                            : "border-signal/50 bg-signal/10 text-signal"}`}>
          GATE {gate}
        </span>
        <span className="text-sm text-ink-mute">
          {gate === "PASS"
            ? "This agent may be promoted."
            : "This agent is blocked from promotion."}
        </span>
      </div>
    </div>
  );
}
