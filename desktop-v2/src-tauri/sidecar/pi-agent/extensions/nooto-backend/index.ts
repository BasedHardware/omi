/**
 * Pi extension: registers the LLM provider for the Nooto coding agent.
 *
 * Two modes, picked by env var:
 *
 * 1. **Direct mode** (`NOOTO_DIRECT_LLM_URL` set) — Pi calls a local
 *    OpenAI-compatible endpoint (vLLM / Ollama / LM Studio) directly. No
 *    Firebase auth, no cloud backend hop. Use this with a self-hosted Qwen3.6
 *    on the local GPU box.
 *
 *    Required env:
 *      NOOTO_DIRECT_LLM_URL   e.g. http://192.168.86.23:8000/v1
 *    Optional env:
 *      NOOTO_DIRECT_LLM_MODEL served model name (default "qwen3.6-35b-a3b")
 *
 * 2. **Cloud mode** (default — `NOOTO_BACKEND_URL` set) — Pi calls the Nooto
 *    backend at `${NOOTO_BACKEND_URL}/v1/agent/code/chat/completions` with the
 *    user's Firebase ID token as a Bearer header. The backend meters credits
 *    and proxies upstream to OpenRouter.
 *
 *    Required env:
 *      NOOTO_BACKEND_URL      e.g. https://nooto-dev.togodynamics.com
 *      NOOTO_ID_TOKEN         Firebase ID token
 */

import type { ExtensionAPI } from "@mariozechner/pi-coding-agent";

const PROVIDER_ID = "nooto-backend";
const DEFAULT_MODEL_ID = "qwen3.6-35b-a3b";

export default function registerNootoBackend(pi: ExtensionAPI): void {
  const directUrl = process.env.NOOTO_DIRECT_LLM_URL;

  if (directUrl) {
    const modelId = process.env.NOOTO_DIRECT_LLM_MODEL ?? DEFAULT_MODEL_ID;
    pi.registerProvider(PROVIDER_ID, {
      baseUrl: directUrl.replace(/\/$/, ""),
      // vLLM / Ollama don't validate the API key by default. Set a literal
      // dummy so the OpenAI SDK's required-key check passes without us
      // shipping a Bearer header the local server doesn't expect.
      apiKey: "EMPTY",
      api: "openai-completions",
      authHeader: true,
      models: [
        {
          id: modelId,
          name: `${modelId} (local)`,
          reasoning: false,
          input: ["text"],
          // Self-hosted: zero per-token cost. Real spend is your electricity.
          cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
          contextWindow: 262_144,
          maxTokens: 8192,
          compat: {
            supportsDeveloperRole: false,
            supportsReasoningEffort: false,
            maxTokensField: "max_tokens",
            // Qwen3 chat template emits <tool_call> blocks; vLLM extracts them
            // when started with --tool-call-parser hermes.
            thinkingFormat: "qwen",
          },
        },
      ],
    });
    return;
  }

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
        id: DEFAULT_MODEL_ID,
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
