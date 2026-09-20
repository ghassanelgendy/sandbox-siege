import { X } from "lucide-react";
import { Chip, Eyebrow, SEV_COLOR } from "./Bits";
import type { Finding } from "../types";

export default function FindingDrawer({
  finding, onClose,
}: { finding: Finding | null; onClose: () => void }) {
  if (!finding) return null;
  const positive = finding.severity === "INFO";

  return (
    <div className="fixed inset-0 z-40 flex justify-end" role="dialog" aria-modal="true">
      <button className="flex-1 bg-ground/70 backdrop-blur-[2px]" onClick={onClose}
              aria-label="Close finding" />
      <aside className="w-full max-w-xl overflow-y-auto border-l border-rule bg-panel p-8">
        <div className="flex items-start justify-between gap-4">
          <div>
            <Eyebrow>{positive ? "Positive finding" : "Finding"}</Eyebrow>
            <h2 className={`mt-1 font-display text-2xl leading-tight ${SEV_COLOR[finding.severity]}`}>
              {finding.title}
            </h2>
          </div>
          <button onClick={onClose}
                  className="border border-rule p-1.5 text-ink-mute hover:text-ink"
                  aria-label="Close">
            <X size={16} />
          </button>
        </div>

        <div className="mt-4 flex flex-wrap gap-2">
          <Chip tone={positive ? "jade" : finding.severity === "CRITICAL" ? "signal" : "sand"}>
            {finding.severity}
          </Chip>
          <Chip tone="mute">{finding.trap_id}</Chip>
          {finding.cve_id && <Chip tone="sand">{finding.cve_id}</Chip>}
          {finding.cvss_score != null && <Chip tone="signal">CVSS {finding.cvss_score}</Chip>}
        </div>

        {/* --- Trap Attribution: Chat -> Tool -> Infrastructure Item (D-41, PRD §8.1) --- */}
        {((finding.chat && finding.chat.length > 0) ||
          (finding.tool_calls && finding.tool_calls.length > 0) ||
          (finding.seed_items && finding.seed_items.length > 0)) && (
          <section className="mt-8 rounded border border-rule-lit/60 bg-ground/60 p-4">
            <Eyebrow>Trap Attribution · Intent → Action → Target</Eyebrow>

            {/* 1. What the agent said (Chat) */}
            {finding.chat && finding.chat.length > 0 && (
              <div className="mt-3">
                <div className="font-mono text-[11px] text-ink-mute uppercase tracking-wider">
                  What the agent said
                </div>
                <div className="mt-1.5 space-y-1.5">
                  {finding.chat.map((c, idx) => (
                    <div
                      key={idx}
                      className="border-l-2 border-jade/60 bg-panel/70 p-2.5 font-mono text-[12px] leading-relaxed text-ink"
                    >
                      <span className="text-ink-mute mr-2 font-semibold">
                        [step {c.step}]
                      </span>
                      "{c.content}"
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* 2. What the agent executed (Tools) */}
            {finding.tool_calls && finding.tool_calls.length > 0 && (
              <div className="mt-4">
                <div className="font-mono text-[11px] text-ink-mute uppercase tracking-wider">
                  Action sequence (Gateway intercepted)
                </div>
                <div className="mt-1.5 space-y-1.5">
                  {finding.tool_calls.map((call, idx) => (
                    <div
                      key={idx}
                      className="flex flex-col gap-1 border border-rule bg-ground p-2.5 font-mono text-[12px]"
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="font-semibold text-sand">
                          step {call.step} · {call.tool}
                        </span>
                        <span
                          className={`px-1.5 py-0.5 text-[10px] font-bold tracking-wider ${
                            call.iam_decision === "ALLOW"
                              ? "bg-jade/10 text-jade"
                              : call.iam_decision === "DENY"
                              ? "bg-signal/15 text-signal"
                              : "text-ink-mute"
                          }`}
                        >
                          IAM: {call.iam_decision}
                        </span>
                      </div>
                      {call.args && Object.keys(call.args).length > 0 && (
                        <div className="text-[11px] text-ink-mute truncate">
                          args: {JSON.stringify(call.args)}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* 3. Which infrastructure resource it hit (Terraform / Seeds) */}
            {finding.seed_items && finding.seed_items.length > 0 && (
              <div className="mt-4">
                <div className="font-mono text-[11px] text-ink-mute uppercase tracking-wider">
                  Targeted Infrastructure (Terraform / Seed)
                </div>
                <div className="mt-1.5 space-y-1.5">
                  {finding.seed_items.map((res, idx) => (
                    <div
                      key={idx}
                      className="border border-sand/30 bg-sand/5 p-2.5 font-mono text-[12px]"
                    >
                      <div className="flex items-center gap-2">
                        <span className="uppercase text-[10px] font-bold text-sand tracking-wider">
                          [{res.kind}]
                        </span>
                        <span className="font-semibold text-ink">{res.name}</span>
                      </div>
                      {res.terraform_source && (
                        <div className="mt-1 text-[11px] text-ink-dim">
                          Matched Terraform source:{" "}
                          <code className="text-sand">{res.terraform_source}</code>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </section>
        )}

        <section className="mt-8">
          <Eyebrow>Evidence</Eyebrow>
          <pre className="mt-2 overflow-x-auto border border-rule bg-ground p-3
                          font-mono text-[12px] leading-relaxed text-ink-dim whitespace-pre-wrap">
{finding.evidence}
          </pre>
        </section>

        <section className="mt-6">
          <Eyebrow>What happened</Eyebrow>
          <p className="mt-2 text-[15px] leading-relaxed text-ink">{finding.explanation}</p>
        </section>

        <section className="mt-6">
          <Eyebrow>Remediation</Eyebrow>
          <p className="mt-2 border-l-2 border-sand/50 pl-3 text-[15px] leading-relaxed text-ink-dim">
            {finding.remediation}
          </p>
        </section>
      </aside>
    </div>
  );
}
