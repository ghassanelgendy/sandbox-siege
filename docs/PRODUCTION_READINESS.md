# Sandbox Siege — Production Readiness Assessment

> **What this is.** A dated, evidence-backed review of whether this hackathon build can be
> released as a public, internet-facing service. It is **not** a product decision — the PRD
> explicitly scopes Sandbox Siege as a *pre-production test harness* (non-goals N1–N5). This
> document records the audit so that anyone deciding to "put it on a domain for the world"
> does so with the facts in front of them.
>
> **Status: 🔴 NOT production-ready as shipped.** The engine is reliably demo-ready and CI-ready,
> but the surface area that makes it *reachable* (Cloudflare tunnel, exposed ports, zero auth)
> is not safe to expose without the checklist in [§ 6](#6-release-checklist) below.

---

## 1. Executive verdict

At **revision `b56fe8d`** (main) the repo is in excellent shape for its stated purpose — a
quantifiable, repeatable agent-safety evaluation you can run on stage and in CI:

- ✅ **The core product works.** 66 backend tests pass (`pytest backend/tests`), covering the
  detectors, scoring, scenario YAML validity, fallback parsing, and the e2e `DENY → escalate →
  ALLOW` sequence that is the product's thesis.
- ✅ **The safety rails hold.** The Gateway is the only path to the sandbox; `http_post` never
  makes a real call; `web_search` is the sole egress tool and the Gateway drops canary/live-credential
  queries before they leave the host (FR-3.5, D-34).
- ✅ **CI is real.** `.github/workflows/siege-gate.yml` reads all keys from GitHub Secrets (no
  hardcoded keys in the *current* workflow), boots LocalStack, runs the gate, uploads artifacts,
  and emails the report via Resend.

But the things that make it *production-shaped* are exactly the things it was built without, and
several are security-critical. Releasing the **demo surface** (UI + API + tunnel) publicly as-is
would allow strangers to spend your model-provider credits, read captured secrets, and use the
backend as a proxy into your network.

---

## 2. Method

Audit performed on 2026-09-20 against the working tree at revision `b56fe8d`:

1. Read the full document set (`AGENTS.md`, `docs/PRD.md`, `docs/FLOW.md`, `PLAN.md`, `README.md`, `USAGE.md`).
2. Read the runtime surface: `main.py`, `config.py`, `gateway.py`, `events.py`, `orchestrator.py`,
   `cloud/localstack.py`, `agent/custom_providers.py`, `generator.py`, `Dockerfile`s, `nginx.conf`,
   `docker-compose.yml`.
3. Ran `pytest backend/tests` (66 passed).
4. Grepped the index **and** the full git history for live credential material
   (provider keys, `re_…` Resend keys, `gsk_…` Groq keys, `.env`).

---

## 3. What already meets production bar

| Id | Evidence |
|---|---|
| **Contract is typed end to end** | `schemas.py` Pydantic models gate every API boundary; frontend `types.ts` mirrors it; all responses validate (FR-9.3). |
| **No hardcoded-ish model roster** | Roster is discovered + health-checked at runtime (FR-4.7); healthy/tool-capable models only. |
| **Graceful provider degradation** | Retries with backoff, `payment_required` not retried, cascading model fallbacks (D-32), run fails with a clear message rather than hanging (NFR-4). |
| **Offline replay path** | `siege replay` re-emits recorded events with zero network calls (FR-8.3) — the demo/leaderboard safety net. |
| **Effective egress discipline** | Only one egress tool, query-cleared by the Gateway, SearXNG isolated on `siege-egress` with no route to LocalStack (FR-3.5, D-34, `docker-compose.yml:80-98`). |
| **Tests gate the thesis** | `FakeBackend` regression-tests the IAM escalation sequence offline (D-13). |
| **CI uses GitHub Secrets** | No key literal in the current `siege-gate.yml`. |

---

## 4. Blockers — do not expose without fixing these

Ordered by severity. Each is a *measured fact about this codebase*, not speculation.

### B1 — Live secrets are committed to git history 🔥

The **current working tree** is mostly clean (`.env` is gitignored, the workflow uses Secrets),
but:

- `testing_apis_info.md` is **still tracked** and contains live Bynara + Dahl API keys
  (violates PRD NFR-5). *Fixed in this change — see § 7.*
- Git history contains the credentials of at least three past `.env` commits and workflow
  updates: **live Resend keys** (`re_…`), a **live Groq key** (`gsk_…`), and Bynara/Dahl keys.
  History was never rewritten.
- `searxng/settings.yml` carries a committed `secret_key` (LOW — SearXNG is not internet-facing,
  but a committed signing secret is still a defect for a public repo).

**Because the repo already has a public remote, assume every rotated key has leaked.** Do not
"just delete the files" — rotate every affected credential and purge history with
`git filter-repo` before the repo goes public.

### B2 — Zero authentication on the entire API 🌐

`siege/main.py` has **no auth middleware**; the Docker image binds `0.0.0.0:18000`
(`backend/Dockerfile:19`); nginx proxies all of `/api/*` to it; the Cloudflare tunnel maps a
public domain onto that nginx. The result: anyone with the URL can call **every** endpoint. For a
public deployment this means:

- **Abuse / spend** — `POST /api/runs` launches a paid model run per request; `POST
  /api/scenarios/generate` burns model tokens. Unauthenticated = unlimited.
- **Secret disclosure** — `GET /api/runs/{id}` returns the full report, and
  `events.jsonl` (via the stream endpoint) contains **raw tool results, including secret values
  the agent read out of Secrets Manager/SSM** (Gateway emits `tool.result` with full `result`,
  `gateway.py:110-114`, persisted verbatim in `events.py:62-64`).
- **Backend SSRF** — `POST /api/providers` accepts an arbitrary `base_url`, and
  `GET /api/models` then health-probes it with a real tool-calling request
  (`main.py:146-167`). A public instance is a proxy into your internal network
  (cloud metadata, Docker socket, LocalStack itself on the same fabric).
- **Locked-down run IDs do not help** — `run_id` is not validated before
  `RUNS_DIR / run_id / "report.json"` (`orchestrator.py:186-191`) or
  `RUNS_DIR / run_id / "events.jsonl"` (`events.py:108-112`); scope is bounded to `runs/` but the
  path is attacker-influenced.

### B3 — No rate limiting, no concurrency guard, blocking handler ⏱️

- `ThreadPoolExecutor(max_workers=2)` (`main.py:32`) caps *running* explorations but quits
  nothing: requests queue indefinitely and each still writes runs + spends tokens.
- `POST /api/scenarios/generate` runs inline on the event loop (`main.py:52-63`) — a burst freezes
  the whole API (NFR-4 is about *provider* outages, not resource exhaustion).

### B4 — LocalStack exposed to the host network 🔓

`docker-compose.yml` publishes **`4566:4566`** and mounts **`/var/run/docker.sock`** into the
container, with `EXTRA_CORS_ALLOWED_ORIGINS=*` (`docker-compose.yml:14-17`). LocalStack's default
edge credentials (`test`/`test`, `cloud/localstack.py:52-57`) mean anyone on the LAN can reach the
sandbox: `/._localstack/state/reset`, create users, read/write resources. Worse, the docker.sock
mount is a standard container-escape vector if that container is ever compromised. The PRD (P0
checklist) already says to drop the socket unless Lambda is used — it is still mounted.

### B5 — No stored-data protection or retention policy 💾

Reports and event tapes live as plaintext JSON under `runs/`, served without access control, and
are never cleaned up (no TTL, no redaction of captured secrets in stored artifacts). "Filesystem
JSON only" is a deliberate non-goal (N5) — fine for a demo, fatal for a hosted service without an
owner.

---

## 5. Secondary gaps (fix as time allows)

| Id | Gap | Notes |
|---|---|---|
| S1 | Container tags are `:latest` / unpinned | Reproducibility & supply chain; pin digests in compose + CI. |
| S2 | No structured logging/metrics/tracing | Debugging a shot tunnel-bound run is read-the-console. |
| S3 | No secrets scanner or dependency-vuln check in CI | A `gitleaks`/`trufflehog` step would have caught B1. |
| S4 | Custom providers persist their API keys to `~/.siege/custom_providers.json` plaintext | Intended for local BYO-model; document that it must not hold shared credentials. |
| S5 | `_enforce_iam_cache` is process-global | Cached across runs; fine single-node, wrong in multi-worker. |
| S6 | CORS is dev-only origins | Correct for local dev now, but any future split-frontend deployment needs a config-driven origin list, not a code edit. |

---

## 6. Release checklist

Use this when the decision *is* to host it publicly (the "AgentFuse" trajectory in the roadmap).

- [ ] **Rotate every credential that ever touched git** (Resend, Groq, Bynara, Dahl, LocalStack
      token) and purge history with `git filter-repo`; add a `gitleaks` pre-commit/CI hook.
- [ ] **Add authentication** (opaque bearer token / OIDC) enforced as FastAPI middleware, and
      remove the ability for unauthenticated callers to reach anything under `/api`.
- [ ] **Add per-user and global rate limits** on `POST /api/runs`, `POST /api/scenarios/generate`,
      and `POST /api/providers`; move `generate` off the event loop.
- [ ] **Close the SSRF** hole in custom providers (block link-local/private ranges, metadata IPs,
      and the LocalStack endpoint in `health_check_model`; require allowlisted schemes/hosts).
- [ ] **Validate + namespace `run_id`** (allow `[A-Za-z0-9_-]`, resolve under `RUNS_DIR`, re-ject
      `..`.
- [ ] **Stop publishing `4566` and drop the docker.sock mount**; give the tunnel only the frontend
      port. Run LocalStack on an internal-only compose network for anything shared.
- [ ] **Redact secrets in stored artifacts** — mask secret-valued tool results in `events.jsonl` /
      reports (or do not persist the full `tool.result` payload by default).
- [ ] **Pin images** (LocalStack, cloudflared, searxng, python, node) to digests.
- [ ] **Set a runs TTL / retention** policy and add data-at-rest protection for `runs/`.

---

## 7. Decisions made in this audit

| # | Decision | Reasoning |
|---|---|---|
| D-38 | **No production release as-shipped.** The build stays a pre-production harness (N1–N5); hosting requires § 6. | The demo and CI paths are excellent; the *reachable* surface is not safe. Keep PRD non-goals honest rather than bolting on a half-auth. |
| D-39 | **Redact, don't delete, `testing_apis_info.md`.** Keys replaced with `.env` pointers; doc kept as provider/model reference. | Preserves useful integration reference while satisfying NFR-5. History is *not* rewritten here — rotation + `filter-repo` tracked separately. |
| D-40 | **Assessment lives as `docs/PRODUCTION_READINESS.md`, linked from PRD/README/AGENTS.** | Targeted docs edits per AGENTS.md; the audit is a living doc, not a decision-log footnote. |