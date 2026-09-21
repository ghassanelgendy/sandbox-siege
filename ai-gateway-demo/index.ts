import dotenv from "dotenv";
dotenv.config({ path: ".env.local" });

import { generateText } from "ai";

if (!process.env.AI_GATEWAY_API_KEY) {
  console.error("AI_GATEWAY_API_KEY is not set. Run ./setup.sh first.");
  process.exit(1);
}

const { text } = await generateText({
  model: "typesafe-ai/jev",
  prompt: "Invent a new holiday and describe its traditions.",
});

console.log(text);
