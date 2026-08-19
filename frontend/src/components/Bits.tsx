import type { ReactNode } from "react";
import type { Grade, Outcome, Severity } from "../types";

export const SEV_COLOR: Record<Severity, string> = {
  CRITICAL: "text-signal",
  HIGH: "text-sand",
  MEDIUM: "text-ink-dim",
  LOW: "text-ink-mute",
  INFO: "text-jade",
};

export const OUTCOME_LABEL: Record<Outcome, string> = {
  pass: "Pass", partial: "Partial", fail: "Fail",
};

export const OUTCOME_COLOR: Record<Outcome, string> = {
  pass: "text-jade", partial: "text-sand", fail: "text-signal",
};

export const GRADE_COLOR: Record<Grade, string> = {
  A: "text-jade", B: "text-jade", C: "text-sand", D: "text-sand", F: "text-signal",
};

export function Eyebrow({ children }: { children: ReactNode }) {
  return <div className="eyebrow">{children}</div>;
}

export function Panel({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <div className={`border border-rule bg-panel ${className}`}>{children}</div>
  );
}

export function Chip({ tone, children }: { tone: "sand" | "signal" | "jade" | "mute"; children: ReactNode }) {
  const tones = {
    sand: "border-sand/45 text-sand bg-sand/8",
    signal: "border-signal/45 text-signal bg-signal/8",
    jade: "border-jade/40 text-jade bg-jade/8",
    mute: "border-rule text-ink-mute",
  };
  return (
    <span className={`inline-flex items-center border px-1.5 py-px font-mono text-[10px]
                      tracking-wider uppercase ${tones[tone]}`}>
      {children}
    </span>
  );
}

/** Severity-weighted dot used in dense lists. */
export function Dot({ outcome }: { outcome: Outcome }) {
  const bg = { pass: "bg-jade", partial: "bg-sand", fail: "bg-signal" }[outcome];
  return <span className={`inline-block h-1.5 w-1.5 rounded-full ${bg}`} />;
}

export function Empty({ title, hint }: { title: string; hint: string }) {
  return (
    <div className="border border-dashed border-rule p-10 text-center">
      <p className="font-display text-lg text-ink-dim">{title}</p>
      <p className="mt-1 text-sm text-ink-mute">{hint}</p>
    </div>
  );
}
