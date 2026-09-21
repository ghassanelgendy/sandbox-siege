# jev-sidecar

Adapter between `backend/siege/jev.py` (a Python `urllib` client expecting a plain
REST `POST /v1/judge` -> `{answer, confidence}` contract) and the only verified
way to actually call Jev: Vercel AI Gateway's Node-only `experimental_evaluate`
SDK function for the `typesafe-ai/jev` model.

## Why this exists

`docs/PRD.md` §8.2 / FR-4.9 originally documented `JEV_BASE_URL` as a direct
TypeSafe REST endpoint (`https://api.typesafe.ai`). No such endpoint has been
verified to exist. The only working integration path found and tested is the
AI SDK's `experimental_evaluate`, which:

- is Node/TypeScript-only (no public raw REST contract),
- requires `ai@^7` and Node 22+,
- is authenticated with `AI_GATEWAY_API_KEY`, not a bearer token at an arbitrary base URL.

This sidecar exposes the REST shape `jev.py` already expects, so the Python
backend needed zero changes. See `docs/PRD.md` decision log (D-44) for the
full rationale.

## Endpoints

- `GET /health` -> `{status: "ok", gatewayConfigured: boolean}`
- `POST /v1/judge` (requires `Authorization: Bearer <JEV_API_KEY>`)
  - body: `{question: string, context: string, type: "boolean"|"choice"|"score", choices?: string[]}`
  - response: `{answer: string, confidence: number}`

## Known limitation

`choice`/`score` questions require per-option `criteria` text on the real
`experimental_evaluate` call, but `jev.py`'s detector rules only ever carry
plain choice labels — no descriptive criteria. This sidecar synthesizes a
generic, unvalidated criteria map for those two types. `boolean` (the default
`answer_type` used everywhere in this repo today) needs no criteria and is
fully verified end-to-end.

## Local dev (outside Docker)

```bash
npm install
AI_GATEWAY_API_KEY=... JEV_API_KEY=... PORT=8090 npm start
```

Requires Node 22+.
