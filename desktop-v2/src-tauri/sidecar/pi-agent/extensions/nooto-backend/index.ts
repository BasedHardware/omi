/**
 * Pi extension: registers the Nooto backend as a custom OpenAI-compatible LLM provider.
 *
 * Every model turn issued by the Pi RPC sidecar is sent to
 *   ${NOOTO_BACKEND_URL}/v1/agent/code/completions
 * with the user's Firebase ID token as a Bearer header. The backend meters
 * credits and proxies to OpenRouter (qwen/qwen3.6-35b-a3b) — Pi never sees
 * the OpenRouter key.
 *
 * Required env vars:
 *   NOOTO_BACKEND_URL  e.g. https://nooto-dev.togodynamics.com
 *   NOOTO_ID_TOKEN     Firebase ID token; passed as Bearer to the backend
 */

import type { ExtensionAPI } from "@mariozechner/pi-coding-agent";

const PROVIDER_ID = "nooto-backend";
const MODEL_ID = "qwen3.6-35b-a3b";

export default function registerNootoBackend(pi: ExtensionAPI): void {
  const backendUrl = process.env.NOOTO_BACKEND_URL;
  if (!backendUrl) throw new Error("NOOTO_BACKEND_URL is required for the nooto-backend Pi extension");
  if (!process.env.NOOTO_ID_TOKEN) throw new Error("NOOTO_ID_TOKEN is required for the nooto-backend Pi extension");

  pi.registerProvider(PROVIDER_ID, {
    baseUrl: `${backendUrl.replace(/\/$/, "")}/v1/agent/code`,
    apiKey: "NOOTO_ID_TOKEN",
    api: "openai-completions",
    authHeader: true,
    models: [
      {
        id: MODEL_ID,
        name: "Qwen3.6 35B-A3B (Nooto)",
        reasoning: false,
        input: ["text"],
        cost: { input: 0.2418, output: 1.4480, cacheRead: 0, cacheWrite: 0 },
        contextWindow: 262_144,
        maxTokens: 8192,
        compat: { supportsDeveloperRole: false, supportsReasoningEffort: false, maxTokensField: "max_tokens" },
      },
    ],
  });
}
