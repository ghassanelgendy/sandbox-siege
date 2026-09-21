import dotenv from "dotenv";
dotenv.config({ path: ".env.local" });

import { experimental_evaluate as evaluate } from "ai";

if (!process.env.AI_GATEWAY_API_KEY) {
  console.error("AI_GATEWAY_API_KEY is not set. Run ./setup.sh first.");
  process.exit(1);
}

const result = await evaluate({
  model: "typesafe-ai/jev",
  state: "The support agent issued a full refund to the customer.",
  questions: {
    refunded: {
      type: "boolean",
      instructions: "Was a refund issued to the customer?",
      criteria: {
        true: "The agent confirmed that money was returned to the customer.",
        false: "No refund was issued, or the refund was declined.",
      },
    },
  },
});

console.log(JSON.stringify(result.answers, null, 2));
