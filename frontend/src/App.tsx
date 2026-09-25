import { useState } from "react";
import { Crosshair } from "lucide-react";
import Launch from "./pages/Launch";
import Console from "./pages/Console";
import ReportCard from "./pages/ReportCard";
import Leaderboard from "./pages/Leaderboard";
import { sampleReport, startRun } from "./api";
import type { Report } from "./types";

type View = "launch" | "console" | "report" | "leaderboard";

const TABS: { id: View; label: string }[] = [
  { id: "launch", label: "Launch" },
  { id: "console", label: "Console" },
  { id: "report", label: "Report" },
  { id: "leaderboard", label: "Leaderboard" },
];

export default function App() {
  const [view, setView] = useState<View>("launch");
  const [runId, setRunId] = useState<string | null>(null);
  const [demo, setDemo] = useState(false);
  // set when a live launch failed and we fell back to the recorded sample (D-16/D-55)
  const [fallbackNotice, setFallbackNotice] = useState<string | null>(null);
  const [report, setReport] = useState<Report | null>(null);

  const launch = async (o: { model: string; provider: string; agentFramework: string; scenarioIds: string[];
                             threshold: number; demo: boolean }) => {
    setDemo(o.demo);
    setReport(null);
    setFallbackNotice(null);
    if (o.demo) {
      setRunId(null);
    } else {
      const res = await startRun({
        model: o.model, provider: o.provider, agent_framework: o.agentFramework,
        scenario_ids: o.scenarioIds, mode: "live", threshold: o.threshold,
      });
      // no backend? fall through to the recorded stream rather than a dead screen --
      // but say so loudly: the sample must never pass for the run that was launched
      setRunId(res?.run_id ?? null);
      if (!res) {
        setDemo(true);
        setFallbackNotice(
          "The live run could not be started (backend unreachable or the request was rejected). " +
          "You are watching the recorded SAMPLE run, not your launch.");
      }
    }
    setView("console");
  };

  // Deliberately does NOT navigate. During a live demo the presenter decides
  // when to leave the console; an auto-jump steals the room's attention.
  const finished = (r: Report | null) => {
    // the fixture is hand-authored and says mode "live"; relabel it so the report card
    // cannot present sample data as a real LocalStack run (D-55)
    setReport(r ?? (demo ? { ...sampleReport, mode: "replay", backend: "sample-fixture" } : null));
  };

  return (
    <div className="min-h-screen">
      <nav className="sticky top-0 z-30 flex h-14 items-center justify-between
                      border-b border-rule bg-ground/95 px-6 backdrop-blur">
        <button onClick={() => setView("launch")} className="flex items-center gap-2.5">
          <Crosshair size={17} className="text-sand" />
          <span className="font-display text-[15px] font-semibold tracking-[0.14em] uppercase text-ink">
            Sandbox Siege
          </span>
        </button>
        <div className="flex items-center gap-1">
          {TABS.map((t) => (
            <button key={t.id} onClick={() => setView(t.id)}
                    disabled={t.id === "report" && !report}
                    className={`px-3 py-1.5 font-display text-[13px] tracking-wide transition-colors
                      ${view === t.id ? "text-ink border-b-2 border-sand"
                                      : "text-ink-mute hover:text-ink-dim"}
                      disabled:cursor-not-allowed disabled:opacity-30`}>
              {t.label}
            </button>
          ))}
        </div>
      </nav>

      <main>
        {view === "launch" && <Launch onLaunch={launch} />}
        {view === "console" && (
          <Console runId={runId} demo={demo} notice={fallbackNotice} onFinished={finished}
                   report={report} onViewReport={() => setView("report")} />
        )}
        {view === "report" && report && <ReportCard report={report} />}
        {view === "leaderboard" && <Leaderboard />}
      </main>

      <footer className="mt-16 border-t border-rule py-6 text-center font-mono text-[11px] text-ink-mute">
        Built by <span className="text-sand font-medium">Team Fo2 El-Sa7ab</span> (Ghassan Elgendy &amp; Ahmed Wagdy) · Sandbox Siege
      </footer>
    </div>
  );
}
