// jev-sidecar — translates backend/siege/jev.py's REST contract (POST /v1/judge,
// {question, context, type, choices} -> {answer, confidence}) into a call to
// Vercel AI Gateway's `experimental_evaluate` for the `typesafe-ai/jev` model.
//
// Why this exists: the only verified way to call Jev is the Node-only AI SDK
// function `experimental_evaluate` (requires Node 22+, AI_GATEWAY_API_KEY).
// jev.py is a Python urllib client built against a plain REST shape. This
// sidecar is the adapter between the two so jev.py stays unchanged. See
// docs/PRD.md §8.2 / FR-4.9 for the documented-plan divergence this covers.
import http from "node:http";
import { experimental_evaluate as evaluate } from "ai";

const PORT = process.env.PORT || 8090;
const JEV_API_KEY = process.env.JEV_API_KEY || "";
const GATEWAY_CONFIGURED = Boolean(process.env.AI_GATEWAY_API_KEY);

function readBody(req) {
  return new Promise((resolve, reject) => {
    let data = "";
    req.on("data", (chunk) => (data += chunk));
    req.on("end", () => resolve(data));
    req.on("error", reject);
  });
}

function buildQuestion(type, question, choices) {
  if (type === "choice") {
    const list = choices && choices.length ? choices : ["yes", "no"];
    return {
      type: "choice",
      instructions: question,
      choices: list,
      // No per-choice description is available from the caller (jev.py's
      // detector rules only carry plain choice labels) — this is a best-effort
      // generic criteria map, not validated against real TypeSafe guidance.
      criteria: Object.fromEntries(
        list.map((c) => [c, `The best-matching category for the state is '${c}'.`])
      ),
    };
  }
  if (type === "score") {
    const levels = choices && choices.length ? choices : ["0", "1", "2", "3"];
    return {
      type: "score",
      instructions: question,
      // Same caveat as choice: generic ordered-level labels, best-effort only.
      criteria: Object.fromEntries(levels.map((l, i) => [l, `Severity level ${i}: ${l}.`])),
    };
  }
  return { type: "boolean", instructions: question };
}

function extractAnswer(result, type) {
  const a = result.answers.q;
  const calibrated = result.providerMetadata?.typesafe?.confidence;
  if (type === "choice") {
    return { answer: a.choice, confidence: calibrated ?? a.probabilities?.[a.choice] ?? 0.5 };
  }
  if (type === "score") {
    const maxProb = a.probabilities ? Math.max(...Object.values(a.probabilities)) : 0.5;
    return { answer: String(a.score), confidence: calibrated ?? maxProb };
  }
  const p = a.probability ?? 0.5;
  return { answer: p >= 0.5 ? "yes" : "no", confidence: p >= 0.5 ? p : 1 - p };
}

const server = http.createServer(async (req, res) => {
  if (req.method === "GET" && req.url === "/health") {
    res.writeHead(200, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ status: "ok", gatewayConfigured: GATEWAY_CONFIGURED }));
    return;
  }

  if (req.method !== "POST" || req.url !== "/v1/judge") {
    res.writeHead(404, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ error: "not found" }));
    return;
  }

  const auth = req.headers.authorization || "";
  if (!JEV_API_KEY || auth !== `Bearer ${JEV_API_KEY}`) {
    res.writeHead(401, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ error: "unauthorized" }));
    return;
  }

  if (!GATEWAY_CONFIGURED) {
    res.writeHead(503, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ error: "AI_GATEWAY_API_KEY not configured" }));
    return;
  }

  try {
    const body = JSON.parse(await readBody(req));
    const { question, context, type, choices } = body;
    if (!question || context === undefined) {
      res.writeHead(400, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ error: "question and context are required" }));
      return;
    }

    const result = await evaluate({
      model: "typesafe-ai/jev",
      state: context,
      questions: { q: buildQuestion(type, question, choices) },
    });

    res.writeHead(200, { "Content-Type": "application/json" });
    res.end(JSON.stringify(extractAnswer(result, type)));
  } catch (err) {
    res.writeHead(502, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ error: String(err?.message || err) }));
  }
});

server.listen(PORT, () => {
  console.log(`jev-sidecar listening on :${PORT} (gateway configured: ${GATEWAY_CONFIGURED})`);
});
