// Omi Provider Extension for pi-mono
//
// Registers "omi" as a provider using OpenAI-compatible completions API.
// All LLM calls route through api.omi.me/v2/chat/completions, giving
// server-side cost tracking, model selection, and billing control.
//
// Issue #6594: Pi-mono harness with Omi API proxy for server-side cost control.

import type { PiExtensionApi } from "@anthropic-ai/pi-mono";

export default function omiProvider(pi: PiExtensionApi) {
  const baseUrl =
    process.env.OMI_API_BASE_URL || "https://api.omi.me/v2";
  const apiKey = process.env.OMI_API_KEY || "";

  pi.registerProvider("omi", {
    api: "openai-completions",
    baseUrl,
    apiKey,
    models: [
      {
        id: "omi-sonnet",
        name: "Omi Sonnet",
        reasoning: true,
        input: ["text"],
        contextWindow: 200_000,
        maxTokens: 16_384,
        // Cost set to 0 client-side — tracked server-side by the backend
        cost: {
          input: 0,
          output: 0,
          cacheRead: 0,
          cacheWrite: 0,
        },
      },
      {
        id: "omi-opus",
        name: "Omi Opus",
        reasoning: true,
        input: ["text"],
        contextWindow: 200_000,
        maxTokens: 16_384,
        cost: {
          input: 0,
          output: 0,
          cacheRead: 0,
          cacheWrite: 0,
        },
      },
    ],
  });
}
