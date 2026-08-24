import { useState, useEffect } from "react";
import { Crosshair } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import Launch from "./pages/Launch";
import Console from "./pages/Console";
import ReportCard from "./pages/ReportCard";
import Leaderboard from "./pages/Leaderboard";
import { sampleReport, startRun } from "./api";
import type { Report } from "./types";

type View = "launch" | "console" | "report" | "leaderboard";

const TABS: { id: View; label: string; keyHint: string }[] = [
  { id: "launch", label: "Launch", keyHint: "1" },
  { id: "console", label: "Console", keyHint: "2" },
  { id: "report", label: "Report", keyHint: "3" },
  { id: "leaderboard", label: "Leaderboard", keyHint: "4" },
];

export default function App() {
  const [view, setView] = useState<View>("launch");
  const [runId, setRunId] = useState<string | null>(null);
  const [demo, setDemo] = useState(false);
  const [report, setReport] = useState<Report | null>(null);
  const [direction, setDirection] = useState<number>(1);

  const changeView = (nextView: View) => {
    if (nextView === view) return;
    const curIdx = TABS.findIndex((t) => t.id === view);
    const nextIdx = TABS.findIndex((t) => t.id === nextView);
    setDirection(nextIdx > curIdx ? 1 : -1);
    setView(nextView);
  };

  // Keyboard navigation: Arrow keys & numbers 1-4 switch tabs
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const activeTag = document.activeElement?.tagName.toLowerCase();
      if (activeTag === "input" || activeTag === "textarea" || activeTag === "select") {
        return;
      }
      const curIdx = TABS.findIndex((t) => t.id === view);
      if (e.key === "ArrowRight" || e.key === "ArrowDown") {
        const nextIdx = (curIdx + 1) % TABS.length;
        if (TABS[nextIdx].id === "report" && !report) return;
        e.preventDefault();
        changeView(TABS[nextIdx].id);
      } else if (e.key === "ArrowLeft" || e.key === "ArrowUp") {
        const prevIdx = (curIdx - 1 + TABS.length) % TABS.length;
        if (TABS[prevIdx].id === "report" && !report) return;
        e.preventDefault();
        changeView(TABS[prevIdx].id);
      } else if (["1", "2", "3", "4"].includes(e.key)) {
        const targetTab = TABS[parseInt(e.key, 10) - 1];
        if (targetTab && (targetTab.id !== "report" || report)) {
          e.preventDefault();
          changeView(targetTab.id);
        }
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [view, report]);

  const launch = async (o: { model: string; provider: string; agentFramework: string; scenarioIds: string[];
                             threshold: number; demo: boolean }) => {
    setDemo(o.demo);
    setReport(null);
    if (o.demo) {
      setRunId(null);
    } else {
      const res = await startRun({
        model: o.model, provider: o.provider, agent_framework: o.agentFramework,
        scenario_ids: o.scenarioIds, mode: "live", threshold: o.threshold,
      });
      // no backend? fall through to the recorded stream rather than a dead screen
      setRunId(res?.run_id ?? null);
      if (!res) setDemo(true);
    }
    changeView("console");
  };

  // Deliberately does NOT navigate. During a live demo the presenter decides
  // when to leave the console; an auto-jump steals the room's attention.
  const finished = (r: Report | null) => {
    setReport(r ?? (demo ? sampleReport : null));
  };

  return (
    <div className="min-h-screen overflow-x-hidden">
      <nav className="sticky top-0 z-30 flex h-14 items-center justify-between
                      border-b border-rule bg-ground/95 px-6 backdrop-blur">
        <button onClick={() => changeView("launch")} className="group flex items-center gap-2.5">
          <Crosshair size={17} className="text-sand transition-transform duration-300 group-hover:rotate-90 group-hover:scale-110" />
          <span className="font-display text-[15px] font-semibold tracking-[0.14em] uppercase text-ink">
            Sandbox Siege
          </span>
        </button>
        <div className="flex items-center gap-1">
          {TABS.map((t) => (
            <button key={t.id} onClick={() => changeView(t.id)}
                    disabled={t.id === "report" && !report}
                    className={`relative px-3 py-1.5 font-display text-[13px] tracking-wide transition-all duration-200
                      ${view === t.id ? "text-ink font-semibold"
                                      : "text-ink-mute hover:text-ink-dim"}
                      disabled:cursor-not-allowed disabled:opacity-30`}>
              <span className="flex items-center gap-1.5">
                {t.label}
                <span className="font-mono text-[9px] px-1 py-0.2 rounded border border-rule bg-panel text-ink-mute">
                  {t.keyHint}
                </span>
              </span>
              {view === t.id && (
                <motion.div
                  layoutId="activeTabUnderline"
                  className="absolute bottom-0 left-0 right-0 h-[2px] bg-sand"
                  transition={{ type: "spring", stiffness: 400, damping: 30 }}
                />
              )}
            </button>
          ))}
          <span className="ml-3 hidden md:inline-flex items-center gap-1 text-[11px] font-mono text-ink-mute bg-panel px-2 py-0.5 border border-rule rounded">
            Use <kbd className="text-sand font-bold">←</kbd> <kbd className="text-sand font-bold">→</kbd> arrows
          </span>
        </div>
      </nav>

      <main className="perspective-3d min-h-[calc(100vh-3.5rem)]">
        <AnimatePresence mode="wait" initial={false}>
          <motion.div
            key={view}
            initial={{ opacity: 0, rotateY: direction * 12, translateZ: -120, scale: 0.96 }}
            animate={{ opacity: 1, rotateY: 0, translateZ: 0, scale: 1 }}
            exit={{ opacity: 0, rotateY: -direction * 12, translateZ: -120, scale: 0.96 }}
            transition={{ duration: 0.35, ease: [0.16, 1, 0.3, 1] }}
            className="w-full h-full transform-gpu"
          >
            {view === "launch" && <Launch onLaunch={launch} />}
            {view === "console" && (
              <Console runId={runId} demo={demo} onFinished={finished}
                       report={report} onViewReport={() => changeView("report")} />
            )}
            {view === "report" && report && <ReportCard report={report} />}
            {view === "leaderboard" && <Leaderboard />}
          </motion.div>
        </AnimatePresence>
      </main>
    </div>
  );
}
