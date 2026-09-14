# Cascading Model & Provider Fallbacks & Branded Report Notifications

> Technical specification for resilient LLM tool execution across rate limits, timeouts, model downtime, and branded CI/CD report card notifications in Sandbox Siege.

---

## 1. Problem & Context

1. **Provider Volatility & Free Tier Limits**:
   - High-throughput scenario test suites (e.g. running all 15 scenarios back-to-back) frequently encounter provider token-per-minute (TPM) caps (e.g., Groq's 8,000 TPM limit) or transient gateway 500/502 errors.
   - Without an automatic fallback tier, any single 429 cooldown or temporary outage halts scenario execution with a fatal `LLM-FAILURE` trap.
2. **Branded Stakeholder Reporting**:
   - CI/CD notifications sent via email must present executive-grade summaries matching Sandbox Siege's terminal cyber aesthetic (`#0B1016` ground, `#E0A458` amber accent, `#6FD3A6` pass jade, `#E5484D` fail red).

---

## 2. Cascading Fallback Architecture

### 2.1 Candidate Selection Strategy (`get_fallback_candidates`)

Located in [`backend/siege/agent/provider.py`](file:///home/batman/sandbox-siege/backend/siege/agent/provider.py):

When a scenario is launched targeting a primary provider and model, Sandbox Siege resolves a prioritized cascade of alternative candidates:

1. **Requested Target**: Primary `(provider, model)` pair.
2. **Intra-Provider Fallbacks**:
   - **Groq**: Alternates across `openai/gpt-oss-120b`, `openai/gpt-oss-20b`, `qwen/qwen3.8-27b`, and `qwen/qwen3.6-27b`.
   - **Dahl**: Alternates across `deepseek-ai/DeepSeek-V4-Flash-0731` and `MiniMaxAI/MiniMax-M2.7`.
   - **Bynara**: Alternates across `deepseek-v4-pro-free` and `mistral-large`.
3. **Cross-Provider Fallbacks**:
   - If the active provider's pool is exhausted or rate-limited, failover cascades to verified secondary providers configured in `.env` (e.g. Groq -> Dahl -> Bynara).

### 2.2 Execution & Seamless Switchover (`chat_with_fallback`)

- `chat_with_fallback` iterates through the candidate chain.
- If a candidate raises an exception (e.g., rate limit, HTTP 500/503, timeout), the runner:
  1. Triggers the `on_fallback` callback.
  2. Emits an event message: `[Siege Fallback] Switched from {failed_p}/{failed_m} to {next_p}/{next_m} due to: ...`.
  3. Updates the scenario runner's active `self.provider` and `self.model`.
  4. Retries the current turn with the new candidate without aborting the scenario or losing conversation context.
- Raises `ProviderError` only if all candidate fallbacks across all providers are exhausted.

---

## 3. Branded HTML Email Reporting

Located in [`.github/workflows/siege-gate.yml`](file:///home/batman/sandbox-siege/.github/workflows/siege-gate.yml):

### 3.1 Design & Aesthetics
- **Color Palette**: Dark terminal theme based on Sandbox Siege design tokens:
  - Background Ground: `#070A0E` / Card Ground: `#0B1016`
  - Accent Amber: `#E0A458`
  - Pass Jade: `#6FD3A6` (with dark pill bg `#1F4738`)
  - Warning Amber: `#E0A458` (with dark pill bg `#6B4E28`)
  - Fail Red: `#E5484D` (with dark pill bg `#5E1F22`)
  - Border Hairlines: `#1E2A36`
- **Header**: High-contrast branding with `SANDBOXSIEGE` logo and gate badge (`GATE PASSED` / `GATE FAILED`).
- **Metric Cards**:
  - **Trust Score**: Final score out of 100 with grade (`A`, `B`, `C`, `D`, `F`) and required threshold.
  - **Pass Rate**: Scenario counts breakdown (`pass` / `warn` / `fail`).
  - **Target Model**: Model and provider under test.
- **Run Metadata**: Repository, branch, commit SHA, and carbon/token efficiency statistics.
- **Scenario Table**: High-density matrix displaying scenario IDs, titles, colored outcome badges, numeric scores, and detected trap pills.
- **Direct Link**: Button navigating directly to GitHub Actions evaluation logs.

### 3.2 Delivery Configuration
- **API**: Resend REST API (`POST https://api.resend.com/emails`).
- **Sender**: `sandbox@ghassan.online` (verified custom domain).
- **Recipient**: `REPORT_EMAIL_TO` secret (default: `ghassanelgendyy@gmail.com`).
- **Error Handling**: Graceful warning if API key or recipient is not configured.

---

## 4. Verification

- Backend fallback tests: `backend/tests/test_fallback.py` (4 tests covering first-try success, multi-step cascade, and all-fail handling).
- Pytest suite: 55 passing unit and integration tests (`pytest backend/tests`).
- TypeScript build: `tsc -b` passes with zero errors.
