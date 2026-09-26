import { useEffect, useState } from "react";
import { Trash2 } from "lucide-react";
import { getLeaderboard } from "../api";
import { Empty, Eyebrow, GRADE_COLOR } from "../components/Bits";
import type { LeaderboardRow, Outcome } from "../types";

const MARK: Record<Outcome, string> = { pass: "●", partial: "◐", fail: "○" };
const MARK_COLOR: Record<Outcome, string> = {
  pass: "text-jade", partial: "text-sand", fail: "text-signal",
};

const STORAGE_KEY = "siege_hidden_leaderboard_runs";

function loadHiddenIds(): Set<string> {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return new Set();
    const parsed = JSON.parse(raw);
    return new Set(Array.isArray(parsed) ? parsed : []);
  } catch {
    return new Set();
  }
}

function saveHiddenIds(ids: Set<string>): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(Array.from(ids)));
  } catch {
    // Ignore storage errors
  }
}

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

function formatRunTime(startedAt?: string, runId?: string): { formatted: string; full: string } {
  let date: Date | null = null;
  if (startedAt) {
    const d = new Date(startedAt);
    if (!isNaN(d.getTime())) {
      date = d;
    }
  }
  if (!date && runId) {
    const m = runId.match(/(?:run|replay)_(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})/);
    if (m) {
      const d = new Date(`${m[1]}-${m[2]}-${m[3]}T${m[4]}:${m[5]}:${m[6]}Z`);
      if (!isNaN(d.getTime())) {
        date = d;
      }
    }
  }
  if (!date) return { formatted: "—", full: "" };

  const pad = (n: number) => n.toString().padStart(2, "0");
  const year = date.getFullYear();
  const month = pad(date.getMonth() + 1);
  const day = pad(date.getDate());
  const hours = pad(date.getHours());
  const minutes = pad(date.getMinutes());

  return {
    formatted: `${year}-${month}-${day} ${hours}:${minutes}`,
    full: date.toISOString(),
  };
}

export default function Leaderboard() {
  const [rows, setRows] = useState<LeaderboardRow[] | null>(null);
  const [hiddenIds, setHiddenIds] = useState<Set<string>>(() => loadHiddenIds());

  useEffect(() => {
    getLeaderboard().then(setRows);
  }, []);

  const hideRun = (runId: string) => {
    setHiddenIds((prev) => {
      const next = new Set(prev);
      next.add(runId);
      saveHiddenIds(next);
      return next;
    });
  };

  const unhideAll = () => {
    const next = new Set<string>();
    setHiddenIds(next);
    saveHiddenIds(next);
  };

  const visibleRows = (rows ?? []).filter((r) => !hiddenIds.has(r.run_id));
  const hiddenCount = (rows ?? []).filter((r) => hiddenIds.has(r.run_id)).length;

  const ids = sortTrapIds(
    Array.from(new Set(visibleRows.flatMap((r) => Object.keys(r.per_scenario))))
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

      {hiddenCount > 0 && visibleRows.length > 0 && (
        <div className="mt-6 flex items-center justify-between border border-rule bg-panel px-4 py-2 font-mono text-[12px] text-ink-dim">
          <span>
            {hiddenCount} {hiddenCount === 1 ? "run" : "runs"} hidden from view
          </span>
          <button
            type="button"
            onClick={unhideAll}
            className="font-mono text-sand hover:underline hover:text-sand/80 transition-colors"
          >
            Unhide all
          </button>
        </div>
      )}

      {rows === null ? (
        <div className="mt-10 h-48 animate-pulse border border-rule bg-panel" />
      ) : rows.length === 0 ? (
        <div className="mt-10">
          <Empty title="No runs recorded yet"
                 hint="Populate the board with: siege seed" />
        </div>
      ) : visibleRows.length === 0 ? (
        <div className="mt-10 space-y-4">
          <Empty
            title="All recorded runs are hidden"
            hint={`${hiddenCount} ${hiddenCount === 1 ? "run is" : "runs are"} currently hidden from the board.`}
          />
          <div className="flex justify-center">
            <button
              type="button"
              onClick={unhideAll}
              className="inline-flex items-center gap-2 border border-sand bg-sand px-4 py-2 font-display text-sm font-semibold text-ground transition hover:bg-sand/90"
            >
              Unhide all runs
            </button>
          </div>
        </div>
      ) : (
        <div className="mt-8 overflow-x-auto border border-rule">
          <table className="w-full border-collapse text-left">
            <thead>
              <tr className="border-b border-rule bg-panel">
                <th className="px-4 py-3 eyebrow">Model</th>
                <th className="px-3 py-3 eyebrow">Time</th>
                <th className="px-3 py-3 eyebrow text-right">Score</th>
                <th className="px-3 py-3 eyebrow">Grade</th>
                {ids.map((id) => (
                  <th key={id} className="px-2 py-3 eyebrow text-center" title={id}>
                    {trapLabel(id)}
                  </th>
                ))}
                <th className="w-10 px-2 py-3 eyebrow text-center" title="Hide run"></th>
              </tr>
            </thead>
            <tbody>
              {visibleRows.map((r) => {
                const time = formatRunTime(r.started_at, r.run_id);
                return (
                  <tr key={r.run_id} className="border-b border-rule last:border-0 hover:bg-panel">
                    <td className="px-4 py-3">
                      <div className="font-mono text-[13px] text-ink">{r.model}</div>
                      <div className="font-mono text-[10px] text-ink-mute">{r.provider}</div>
                    </td>
                    <td
                      className="px-3 py-3 font-mono text-[11px] text-ink-dim whitespace-nowrap"
                      title={time.full || undefined}
                    >
                      {time.formatted}
                    </td>
                    <td className="px-3 py-3 text-right font-display text-xl tabular-nums text-ink">
                      {r.trust_score}
                    </td>
                    <td className={`px-3 py-3 font-display text-xl font-semibold ${GRADE_COLOR[r.grade]}`}>
                      {r.grade}
                    </td>
                    {ids.map((id) => {
                      const o = r.per_scenario[id];
                      return (
                        <td key={id} className="px-2 py-3 text-center" title={id}>
                          <span className={o ? MARK_COLOR[o] : "text-rule"}>
                            {o ? MARK[o] : "·"}
                          </span>
                        </td>
                      );
                    })}
                    <td className="px-2 py-3 text-center">
                      <button
                        type="button"
                        onClick={() => hideRun(r.run_id)}
                        title="Hide run from leaderboard"
                        aria-label={`Hide ${r.model} run`}
                        className="inline-flex items-center justify-center rounded p-1.5 text-ink-mute hover:text-signal hover:bg-ground/60 transition-colors"
                      >
                        <Trash2 size={13} />
                      </button>
                    </td>
                  </tr>
                );
              })}
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
