# CLAUDE.md

**All rules for this repository live in [`AGENTS.md`](AGENTS.md). Read it before your first edit.**

It is shared with the other agent tooling used on this project (Antigravity, Cursor), so it is the single place rules are maintained. Do not duplicate rules here — add them to `AGENTS.md`.

## The rule you must not miss

> **If you make any decision that diverges from the documented plan, update the affected document in the same change that introduces the divergence.**
>
> Code that contradicts the docs is a defect, even if it works.

Which doc to update, what counts as a divergence, and the definition of done are all in [`AGENTS.md` §0](AGENTS.md).

## Reading order for a new session

1. [`docs/FLOW.md`](docs/FLOW.md) — end-to-end walkthrough with example payloads
2. [`docs/PRD.md`](docs/PRD.md) — numbered requirements, the specification of record
3. [`PLAN.md`](PLAN.md) — timeline, gates, and the pre-agreed cut order
4. [`AGENTS.md`](AGENTS.md) — working agreements, conventions, safety rails
