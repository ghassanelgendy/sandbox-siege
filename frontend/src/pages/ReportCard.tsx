import { useState } from "react";
import { Bar, BarChart, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { Finding, Report } from "../types";
import ScoreGauge from "../components/ScoreGauge";
import ScenarioCard from "../components/ScenarioCard";
import FindingDrawer from "../components/FindingDrawer";
import { Eyebrow, Panel } from "../components/Bits";

const OUTCOME_FILL: Record<string, string> = {
  pass: "var(--color-jade)", partial: "var(--color-sand)", fail: "var(--color-signal)",
};

export default function ReportCard({ report }: { report: Report }) {
  const [finding, setFinding] = useState<Finding | null>(null);
  const e = report.efficiency;

  const chart = report.scenarios.map((s) => ({
    id: s.id.replace("SIEGE-", ""),
    scored: s.score, forfeited: s.max_score - s.score, outcome: s.outcome,
  }));

  return (
    <div className="mx-auto max-w-6xl px-8 py-12">
      <Eyebrow>Report card · {report.run_id}</Eyebrow>
      <h1 className="mt-1 font-display text-3xl text-ink">
        {report.model} <span className="text-ink-mute">· agent: {report.agent_framework || "raw_llm"} · {report.provider}</span>
      </h1>
      <p className="mt-1 font-mono text-[12px] text-ink-mute">
        {report.backend} · {report.mode} · {report.duration_s}s ·
        {" "}{report.totals.passed} passed / {report.totals.partial} partial / {report.totals.failed} failed
      </p>

      <div className="mt-10 grid gap-10 lg:grid-cols-[minmax(0,1fr)_320px]">
        <Panel className="p-8"><ScoreGauge score={report.trust_score} grade={report.grade}
                                          gate={report.gate} threshold={report.threshold} /></Panel>

        <div className="space-y-4">
          <Panel className="p-5">
            <Eyebrow>Permission layer</Eyebrow>
            <dl className="mt-3 space-y-2 font-mono text-[12px]">
              <div className="flex justify-between">
                <dt className="text-ink-mute">calls IAM denied</dt>
                <dd className="text-sand tabular-nums">{report.iam.denied_calls}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-ink-mute">allowed after escalation</dt>
                <dd className="text-signal tabular-nums">{report.iam.allowed_after_escalation}</dd>
              </div>
            </dl>
            {report.iam.allowed_after_escalation > 0 && (
              <p className="mt-3 border-t border-rule pt-3 text-sm leading-relaxed text-ink-dim">
                IAM held the boundary until the agent replaced its credential. After that
                it permitted everything — correctly.
              </p>
            )}
          </Panel>

          <Panel className="p-5">
            <Eyebrow>Efficiency</Eyebrow>
            <dl className="mt-3 space-y-2 font-mono text-[12px]">
              {[["tool calls", e.tool_calls], ["redundant", e.redundant_calls],
                ["tokens", e.tokens_in + e.tokens_out],
                ["energy", `${e.est_wh} Wh`], ["carbon", `${e.est_gco2e} gCO₂e`]].map(([k, v]) => (
                <div key={String(k)} className="flex justify-between">
                  <dt className="text-ink-mute">{k}</dt>
                  <dd className="text-ink tabular-nums">{v}</dd>
                </div>
              ))}
            </dl>
            <p className="mt-3 border-t border-rule pt-3 text-[11px] leading-relaxed text-ink-mute">
              Estimated at 12 W per vCPU and 462 gCO₂e/kWh. Both figures are assumptions,
              shown so you can substitute your own.
            </p>
            {e.waste_flags.length > 0 && (
              <ul className="mt-2 font-mono text-[11px] text-sand">
                {e.waste_flags.map((f) => <li key={f}>▲ {f}</li>)}
              </ul>
            )}
          </Panel>
        </div>
      </div>

      <div className="mt-12">
        <Eyebrow>Score by scenario</Eyebrow>
        <div className="mt-3 h-44 border border-rule bg-panel p-4">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chart} margin={{ top: 4, right: 4, bottom: 0, left: -22 }}>
              <XAxis dataKey="id" stroke="var(--color-ink-mute)"
                     tick={{ fontSize: 11, fontFamily: "var(--font-mono)" }} tickLine={false} />
              <YAxis stroke="var(--color-ink-mute)"
                     tick={{ fontSize: 11, fontFamily: "var(--font-mono)" }}
                     tickLine={false} axisLine={false} />
              <Tooltip cursor={{ fill: "rgb(255 255 255 / 0.04)" }}
                       contentStyle={{ background: "var(--color-panel-2)",
                                       border: "1px solid var(--color-rule-lit)",
                                       fontFamily: "var(--font-mono)", fontSize: 12 }} />
              <Bar dataKey="scored" stackId="a">
                {chart.map((c) => <Cell key={c.id} fill={OUTCOME_FILL[c.outcome]} />)}
              </Bar>
              <Bar dataKey="forfeited" stackId="a" fill="var(--color-rule)" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="mt-12">
        <Eyebrow>Scenarios — click a finding for evidence</Eyebrow>
        <div className="mt-3 grid gap-4 md:grid-cols-2">
          {report.scenarios.map((s) => (
            <ScenarioCard key={s.id} s={s} onFinding={setFinding} />
          ))}
        </div>
      </div>

      <FindingDrawer finding={finding} onClose={() => setFinding(null)} />
    </div>
  );
}
