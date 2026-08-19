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

        <div className="mt-4 flex gap-2">
          <Chip tone={positive ? "jade" : finding.severity === "CRITICAL" ? "signal" : "sand"}>
            {finding.severity}
          </Chip>
          <Chip tone="mute">{finding.trap_id}</Chip>
        </div>

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
