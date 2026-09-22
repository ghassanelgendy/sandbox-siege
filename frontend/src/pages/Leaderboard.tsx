import { useEffect, useState } from "react";
import { getLeaderboard } from "../api";
import { Empty, Eyebrow, GRADE_COLOR } from "../components/Bits";
import type { LeaderboardRow, Outcome } from "../types";

const MARK: Record<Outcome, string> = { pass: "●", partial: "◐", fail: "○" };
const MARK_COLOR: Record<Outcome, string> = {
  pass: "text-jade", partial: "text-sand", fail: "text-signal",
};
function trapLabel(id: string): string {
  const custom = id.match(/^SIEGE-CUSTOM-(.+)$/);
  if (custom) return `C-${custom[1]}`;
  return id.replace("SIEGE-", "");
}

function sortTrapIds(ids: string[]): string[] {
  return [...ids].sort((a, b) => {
    const na = Number(a.replace("SIEGE-", ""));
    const nb = Number(b.replace("SIEGE-", ""));
    const aNum = !Number.isNaN(na), bNum = !Number.isNaN(nb);
    if (aNum && bNum) return na - nb;
    if (aNum !== bNum) return aNum ? -1 : 1;
    return a.localeCompare(b);
  });
}

export default function Leaderboard() {
  const [rows, setRows] = useState<LeaderboardRow[] | null>(null);
  useEffect(() => { getLeaderboard().then(setRows); }, []);

  const ids = sortTrapIds(
    Array.from(new Set((rows ?? []).flatMap((r) => Object.keys(r.per_scenario))))
  );

  return (
    <div className="mx-auto max-w-5xl px-8 py-12">
      <Eyebrow>Comparative results</Eyebrow>
      <h1 className="mt-1 max-w-2xl font-display text-4xl leading-tight text-ink">
        Same benchmark traps. Different failures.
      </h1>
      <p className="mt-3 max-w-xl leading-relaxed text-ink-dim">
        Every model here was given identical tasks, identical tools and identical
        credentials. What separates them is judgement.
      </p>

      {rows === null ? (
        <div className="mt-10 h-48 animate-pulse border border-rule bg-panel" />
      ) : rows.length === 0 ? (
        <div className="mt-10">
          <Empty title="No runs recorded yet"
                 hint="Populate the board with: siege seed" />
        </div>
      ) : (
        <div className="mt-10 overflow-x-auto border border-rule">
          <table className="w-full border-collapse text-left">
            <thead>
              <tr className="border-b border-rule bg-panel">
                <th className="px-4 py-3 eyebrow">Model</th>
                <th className="px-3 py-3 eyebrow text-right">Score</th>
                <th className="px-3 py-3 eyebrow">Grade</th>
                {ids.map((id) => (
                  <th key={id} className="px-2 py-3 eyebrow text-center" title={id}>
                    {trapLabel(id)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.run_id} className="border-b border-rule last:border-0 hover:bg-panel">
                  <td className="px-4 py-3">
                    <div className="font-mono text-[13px] text-ink">{r.model}</div>
                    <div className="font-mono text-[10px] text-ink-mute">{r.provider}</div>
                  </td>
                  <td className="px-3 py-3 text-right font-display text-xl tabular-nums text-ink">
                    {r.trust_score}
                  </td>
                  <td className={`px-3 py-3 font-display text-xl font-semibold ${GRADE_COLOR[r.grade]}`}>
                    {r.grade}
                  </td>
                  {IDS.map((id) => {
                    const o = r.per_scenario[id];
                    return (
                      <td key={id} className="px-2 py-3 text-center">
                        <span className={o ? MARK_COLOR[o] : "text-rule"}>
                          {o ? MARK[o] : "·"}
                        </span>
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <p className="mt-4 font-mono text-[11px] text-ink-mute">
        ● pass　◐ partial　○ fail
      </p>
    </div>
  );
}
