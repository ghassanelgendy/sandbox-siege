import dotenv from "dotenv";
dotenv.config({ path: ".env.local" });
import { experimental_evaluate as evaluate } from "ai";

// Test 1: boolean without criteria
try {
  const r1 = await evaluate({
    model: "typesafe-ai/jev",
    state: "The server returned a 500 error to the client.",
    questions: { q1: { type: "boolean", instructions: "Did the request fail?" } },
  });
  console.log("boolean no-criteria OK:", JSON.stringify(r1.answers));
} catch (e) { console.log("boolean no-criteria FAILED:", e.message); }

// Test 2: choice without per-choice criteria, just a plain array
try {
  const r2 = await evaluate({
    model: "typesafe-ai/jev",
    state: "The customer asked about a billing discrepancy on their invoice.",
    questions: { q2: { type: "choice", instructions: "Which department should handle this?", choices: ["billing", "technical", "account"] } },
  });
  console.log("choice array-choices OK:", JSON.stringify(r2.answers));
} catch (e) { console.log("choice array-choices FAILED:", e.message); }

// Test 3: score without criteria
try {
  const r3 = await evaluate({
    model: "typesafe-ai/jev",
    state: "The agent deleted a production database without confirmation.",
    questions: { q3: { type: "score", instructions: "Rate the severity of this action from 0 to 3." } },
  });
  console.log("score no-criteria OK:", JSON.stringify(r3.answers));
} catch (e) { console.log("score no-criteria FAILED:", e.message); }
