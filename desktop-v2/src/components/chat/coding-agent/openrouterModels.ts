/**
 * OpenRouter models offered in the coding-agent picker.
 *
 * Keep in sync with `desktop-v2/src-tauri/sidecar/pi-agent/extensions/nooto-backend/index.ts`
 * — Pi must register every id we expose here, or its --model flag will reject.
 */

export interface OpenRouterModel {
  id: string;
  name: string;
  /** USD per million input tokens (display only — real cost comes from OpenRouter). */
  input: number;
  /** USD per million output tokens. */
  output: number;
}

export const OPENROUTER_MODELS: OpenRouterModel[] = [
  { id: "anthropic/claude-sonnet-4.5", name: "Claude Sonnet 4.5", input: 3, output: 15 },
  { id: "anthropic/claude-opus-4-7", name: "Claude Opus 4.7", input: 15, output: 75 },
  { id: "openai/gpt-4o", name: "GPT-4o", input: 2.5, output: 10 },
  { id: "openai/gpt-4o-mini", name: "GPT-4o-mini", input: 0.15, output: 0.6 },
  { id: "qwen/qwen3-coder", name: "Qwen3-Coder", input: 0.2, output: 0.8 },
  // Self-hosted vLLM. The `local/` prefix tells the backend to route to
  // AGENT_CODE_LOCAL_LLM_URL instead of OpenRouter; the prefix is stripped
  // before the upstream call so vLLM sees the served-model-name.
  { id: "local/qwen3.6-27b", name: "Qwen3.6 27B (local)", input: 0, output: 0 },
  { id: "local/qwen3.6-27b-thinking", name: "Qwen3.6 27B Thinking (local)", input: 0, output: 0 },
];

export const DEFAULT_MODEL_ID = OPENROUTER_MODELS[0]!.id;

export function findModel(id: string): OpenRouterModel | undefined {
  return OPENROUTER_MODELS.find((m) => m.id === id);
}
