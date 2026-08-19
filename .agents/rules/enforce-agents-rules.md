# Rule: Enforce AGENTS.md Guidelines

You must strictly adhere to the guidelines, conventions, constraints, and contracts defined in the project's root [AGENTS.md](file:///home/batman/sandbox-siege/AGENTS.md) in all sessions.

## Mandatory Core Rules

1. **Document-First Sync Rule:** 
   * If you make any decision that diverges from the documented plan, you **must** update the affected document in the same change/commit that introduces the divergence.
   * Code that contradicts the docs is a **defect**, regardless of whether the code works.
   * Update [`docs/PRD.md`](file:///home/batman/sandbox-siege/docs/PRD.md) for requirements/scoring/constants.
   * Update [`PLAN.md`](file:///home/batman/sandbox-siege/PLAN.md) for timeline/sequencing/scope cuts.
   * Update [`docs/FLOW.md`](file:///home/batman/sandbox-siege/docs/FLOW.md) for data flow/lifecycles.
   * Update [`README.md`](file:///home/batman/sandbox-siege/README.md) for configuration/run instructions.

2. **Frozen Contract Rule:**
   * [`backend/siege/schemas.py`](file:///home/batman/sandbox-siege/backend/siege/schemas.py) and [`frontend/src/types.ts`](file:///home/batman/sandbox-siege/frontend/src/types.ts) **must** stay mirror images. If you update one, you must update the other and the sample fixture [`fixtures/report_sample.json`](file:///home/batman/sandbox-siege/backend/fixtures/report_sample.json) in the same commit.

3. **Safety Rails & Environment Conventions:**
   * **Never** point this system at real AWS credentials. LocalStack only.
   * Keep detectors pure (no I/O, no mutation) and unit-testable.
   * The `http_post` tool must never make real outbound requests (record and return synthetic 200).
   * Ensure credentials bait remains real *within LocalStack only*.

4. **Definition of Done:**
   * Verify changes using automated tests (`make test`) and run live scenarios or replay (`siege run` / `siege replay`).
   * A change is complete only when code runs, docs are synchronized, decisions are added to the Decision Log (PRD §15), and commit message names the updated docs.

5. **Active Git Auto-Commit Hook:**
   * A lifecycle hook is configured in [`.agents/hooks.json`](file:///home/batman/sandbox-siege/.agents/hooks.json) to automatically run `git add -A` and `git commit` after *every* tool invocation step during development.
   * This keeps a granular history of the workspace modifications during developer agent iterations.
