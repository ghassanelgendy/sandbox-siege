/**
 * Mirrors backend/siege/schemas.py EXACTLY.
 * Changing one without the other breaks the build — see AGENTS.md §3.
 */

export type Severity = "CRITICAL" | "HIGH" | "MEDIUM" | "LOW" | "INFO";
export type Outcome = "pass" | "partial" | "fail";
export type Decision = "ALLOW" | "WARN" | "DENY";
export type Grade = "A" | "B" | "C" | "D" | "F";
export type Gate = "PASS" | "FAIL";
export type Mode = "live" | "replay";

export interface SiegeEvent {
  seq: number;
  ts: string;
  run_id: string;
  scenario_id: string | null;
  type: string;
  data: Record<string, any>;
}

export interface ChatLine {
  role: "agent" | "user" | "system";
  content: string;
  step: number;
}

export interface AttributedCall {
  step: number;
  tool: string;
  args: Record<string, any>;
  iam_decision: "ALLOW" | "DENY" | "N/A";
  resource: string;
}

export interface SeedItemRef {
  kind: string;
  name: string;
  terraform_source?: string | null;
}

export interface Finding {
  trap_id: string;
  severity: Severity;
  title: string;
  evidence: string;
  explanation: string;
  remediation: string;
  step: number;
  cve_id?: string | null;
  cvss_score?: number | null;
  cwe_id?: string | null;
  atlas_id?: string | null;
  confidence?: number | null;
  chat?: ChatLine[];
  tool_calls?: AttributedCall[];
  seed_items?: SeedItemRef[];
}

export interface ScenarioResult {
  id: string;
  title: string;
  severity: Severity;
  weight: number;
  outcome: Outcome;
  score: number;
  max_score: number;
  findings: Finding[];
  timeline: SiegeEvent[];
  steps_used: number;
  duration_s: number;
  error: string | null;
  cve_id?: string | null;
}

export interface Efficiency {
  tool_calls: number;
  redundant_calls: number;
  tokens_in: number;
  tokens_out: number;
  provisioned_vcpu_hours: number;
  est_wh: number;
  est_gco2e: number;
  waste_flags: string[];
}

export interface Report {
  run_id: string;
  model: string;
  provider: string;
  agent_framework: string;
  backend: string;
  mode: Mode;
  started_at: string;
  duration_s: number;
  trust_score: number;
  grade: Grade;
  gate: Gate;
  threshold: number;
  totals: { passed: number; partial: number; failed: number; max_score: number };
  iam: { denied_calls: number; allowed_after_escalation: number };
  efficiency: Efficiency;
  scenarios: ScenarioResult[];
}

export interface ScenarioInfo {
  id: string;
  title: string;
  severity: Severity;
  weight: number;
  description: string;
  trap_summary: string;
  cve_id?: string | null;
}

export interface CustomProvider {
  id: string;
  name: string;
  base_url: string;
  api_key?: string;
  models?: string[];
}

export interface ModelInfo {
  id: string;
  provider: string;
  healthy: boolean;
  supports_tools: boolean;
  error: string | null;
}

export interface LeaderboardRow {
  model: string;
  provider: string;
  trust_score: number;
  grade: Grade;
  run_id: string;
  per_scenario: Record<string, Outcome>;
}

export interface RunResponse {
  run_id: string;
  status: string;
  stream_url: string;
}

export interface GenerateTrapRequest {
  prompt: string;
  provider?: string;
  model?: string;
  terraform_yaml?: string;
}

export interface HealthResponse {
  ok: boolean;
  localstack: boolean;
  enforce_iam: boolean;
  version: string;
}

/** Event type constants — mirrors schemas.EventType. */
export const EV = {
  RUN_STARTED: "run.started",
  SCENARIO_STARTED: "scenario.started",
  AGENT_MESSAGE: "agent.message",
  TOOL_CALLED: "tool.called",
  IAM_VERDICT: "iam.verdict",
  POLICY_VERDICT: "policy.verdict",
  TOOL_RESULT: "tool.result",
  TRAP_TRIGGERED: "trap.triggered",
  SCENARIO_FINISHED: "scenario.finished",
  RUN_FINISHED: "run.finished",
  RUN_ERROR: "run.error",
} as const;
