# AGENTS.md — Rules for AI agents working in this repository

> This file is read automatically by Antigravity, Claude Code, Cursor, and other agent tooling.
> **Read it before your first edit in a session.** [`CLAUDE.md`](CLAUDE.md) points here.

---

## 0. The one rule that matters most: documentation is the source of truth

This project is built by two people in 25 hours using AI agents in parallel, across different tools and machines. **The documents are how we stay in sync — they are not decoration, and they are not written after the fact.**

### The sync rule

> **If you make any decision that diverges from the documented plan, you must update the affected document in the same change that introduces the divergence.**
>
> Code that contradicts the docs is a **defect**, regardless of whether the code works.

**This is not optional and does not require asking permission.** Updating the docs is part of the task, not a follow-up to it.

### What counts as a divergence (non-exhaustive)

| Category | Examples |
|---|---|
| **Contract** | Renaming a field, adding/removing an event type, changing a payload shape, adding an endpoint |
| **Behavior** | Changing scoring weights, thresholds, grade boundaries, pass/partial/fail criteria |
| **Scope** | Cutting a scenario, deferring a feature, adding something not in the PRD |
| **Stack** | Adding, removing, or swapping a dependency |
| **Scenarios** | Changing seeded resources, task prompts, granted IAM policies, detectors |
| **Constants** | Step caps, timeouts, carbon coefficients, retry counts |

### Which document to update

| You changed… | Update |
|---|---|
| A requirement, contract, scenario, detector, scoring rule, or constant | [`docs/PRD.md`](docs/PRD.md) |
| Sequencing, scope, timeline, or what got cut | [`PLAN.md`](PLAN.md) |
| The shape of data moving through the system, or a step in the run lifecycle | [`docs/FLOW.md`](docs/FLOW.md) |
| A decision made *instead of* a documented one | [`docs/PRD.md` §15 Decision log](docs/PRD.md) — add a row with the reasoning |
| How to run, install, or configure anything | [`README.md`](README.md) |

### Definition of done for any task

A change is complete only when:

- [ ] The code works and has been run at least once.
- [ ] Any divergence from the docs is reflected in the docs.
- [ ] New decisions are added to the **Decision log** (PRD §15) with the *why*, not just the *what*.
- [ ] The commit message names the documents updated.

### If you are unsure whether something is a divergence

**It is.** Update the doc. An unnecessary doc update costs thirty seconds; an undocumented one costs your teammate an hour of confusion at 3am.

### What NOT to do

- ❌ Do not silently "improve" a documented design because you prefer a different approach. Change the doc first, then the code.
- ❌ Do not leave a `TODO: update docs` comment. Update them now.
- ❌ Do not rewrite documents wholesale. Make targeted edits — your teammate is reading these concurrently.
- ❌ Do not delete decision-log rows. Supersede them with a new row referencing the old one.

---

## 1. Read these first, in this order

| Order | Document | What it gives you |
|---|---|---|
| 1 | [`docs/FLOW.md`](docs/FLOW.md) | The end-to-end walkthrough with example payloads — read this to understand *what the system does* |
| 2 | [`docs/PRD.md`](docs/PRD.md) | Numbered, testable requirements — the specification of record |
| 3 | [`PLAN.md`](PLAN.md) | Timeline, phases, gates, and the pre-agreed cut order |

If FLOW and PRD ever disagree, **PRD wins** — and fix FLOW in the same change.

---

## 2. What this project is

**Sandbox Siege** — chaos engineering for AI agents. It runs an autonomous DevOps agent against a LocalStack Pro sandbox seeded with deliberate traps, intercepts every action, and issues a **Trust Score** with a safety report card.

Built for DevOpsDays Cairo 2026 Hackathon (Track 1). **The live demo is the top priority** — reliability of the demo path outranks feature breadth in every trade-off.

### The core architectural invariant

The agent under test **never** talks to LocalStack directly. Every action passes through `siege/gateway.py`, which records it, judges it behaviorally, then forwards it to LocalStack — where IAM independently permits or denies.

Two verdicts per action:
- **L1 (IAM)** — *was this permitted?* — LocalStack `ENFORCE_IAM=1`
- **L2 (behavioral)** — *was this wise?* — Siege detectors

**Never bypass the Gateway.** If a tool call reaches boto3 without passing through it, the run is unobservable and the product does not work.

---

## 3. Working agreements

### Ownership
| Area | Owner |
|---|---|
| `backend/siege/**`, scenarios, detectors, scoring, CLI | **A (backend)** |
| `frontend/**`, all UI/UX | **B (frontend)** |
| `docs/**`, `PLAN.md`, `AGENTS.md` | **Both** — whoever makes the change |

Do not edit the other person's area without telling them. The exception is `backend/siege/schemas.py` and `frontend/src/types.ts`, which **must stay mirror images** — changing one without the other breaks the build.

### The frozen contract
`backend/siege/schemas.py` and `backend/fixtures/report_sample.json` were frozen at hour 1. The frontend builds against the fixture and must never be blocked on backend availability.

**Changing the contract is allowed but expensive.** If you must:
1. Update `schemas.py`
2. Update `frontend/src/types.ts` to match
3. Update `fixtures/report_sample.json`
4. Update the contract tables in `docs/PRD.md` §9 and `docs/FLOW.md`
5. Tell your teammate immediately — do not let them discover it via a broken build

### Scope discipline
The cut order is pre-agreed in [`PLAN.md`](PLAN.md) and PRD §14: **SIEGE-007 → SIEGE-006 → leaderboard → GitHub Action → live mode.**

**Never cut:** replay mode, the report card, or scenarios 001 / 002 / 004.

Do not add features that are not in the PRD. If you believe something is missing, add it to the PRD with reasoning *first*.

---

## 4. Technical conventions

### Python (backend)
- Python 3.13, FastAPI, Pydantic v2, `boto3`, `openai`, `typer`, `sse-starlette`
- Type-hint everything. Pydantic models for all data crossing a boundary.
- Tools return `{ok: bool, ...}` — **never raise into the agent loop**. A tool error is data the model must see and react to.
- Detectors are pure functions over the action trace: no I/O, no mutation. This keeps them unit-testable without a sandbox.

### TypeScript (frontend)
- React 18, Vite, TypeScript, Tailwind, Recharts, `lucide-react`, `framer-motion`
- `src/types.ts` mirrors `schemas.py` exactly — same field names, same optionality
- Every screen implements loading, empty, and error states. **A blank screen during a live demo reads as a crash.**

### Safety rails — non-negotiable
- **Never** point this system at real AWS credentials. LocalStack only, always.
- `http_post` must never make a real outbound request. It records and returns a synthetic `200`.
- Secrets live in `.env` and are never committed. `testing_apis_info.md` currently contains live API keys and **is tracked by git** — move them to `.env` before this repo goes public.
- The "admin credentials" seeded as bait are real *within LocalStack only*. They must never resemble a real-world key that could be pasted somewhere dangerous.

---

## 5. Verification before you call something done

```bash
make up                # LocalStack Pro with ENFORCE_IAM=1
siege doctor           # every check green, including ENFORCE_IAM: active
pytest backend/tests   # detectors, scoring, scenario YAML validity
siege run --model deepseek-v4-pro-free --scenario SIEGE-001
```

Then confirm in the browser at `localhost:5173` that the run streams, the trap card fires, and the report renders.

**Do not report a task as complete on the strength of the code compiling.** Run it.

---

## 6. Known environment facts (verified — do not re-derive)

- **LocalStack** requires `LOCALSTACK_AUTH_TOKEN` since March 2026. We hold a **student license = Ultimate-tier service access**, so RDS, EC2, CloudWatch Logs, and `ENFORCE_IAM=1` are all available.
- **Provider health is volatile.** On Bynara, `claude-*` and `gpt-5.5` currently return `payment_required` (insufficient credits) and `qwen-3.8-max-free` returns 502. **Confirmed working with tool-calling:** `deepseek-v4-pro-free`, `mistral-large` (Bynara), `moonshotai/Kimi-K2.6`, `MiniMaxAI/MiniMax-M2.7` (Dahl).
- **Never hardcode the model roster.** Discover it via `/v1/models` and health-check it — see PRD FR-4.7.
- Both providers are **OpenAI-compatible**; use the `openai` SDK with a `base_url` override. LiteLLM was deliberately dropped (PRD §15, D-2).
