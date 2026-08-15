import type { ChatGenerationLivenessPolicy } from "./generation-supervisor";

/**
 * Liveness deadlines for a real model behind the local model gateway
 * (`OMI_CHAT_MODEL=real`, `integration/local-model-gateway.mjs`).
 *
 * The default policy in `generation-supervisor.ts` allows 100ms to the first
 * event and 1s to the whole run, which fits the canned local test gateway
 * because it answers instantly. A real model does not. Measured against
 * GLM-4.7 on 2026-08-15, a one-sentence question streamed 280 reasoning
 * tokens before its first `delta.content`, and the gateway generation source
 * only observes content deltas — so with the default policy every real-model
 * generation finalized `generation_timeout` and chat rendered no answer.
 *
 * These deadlines bound a slow provider without pretending a hung one is fine:
 * 60s to the first observed content covers a long reasoning preamble, 5
 * minutes caps the run, and a 5s heartbeat keeps the surface's stream alive
 * while the model thinks. The canned default is untouched.
 */
export const REAL_MODEL_GENERATION_LIVENESS: ChatGenerationLivenessPolicy = Object.freeze({
  firstEventDeadlineMs: 60_000,
  maxRunDurationMs: 300_000,
  heartbeatIntervalMs: 5_000,
  cancelGraceMs: 2_000,
});

/**
 * Selects the liveness policy for a dev boot from `OMI_CHAT_MODEL`. `null`
 * means "leave the service default alone" — only an explicit real-model run
 * moves the deadlines.
 */
export const resolveDevGenerationLiveness = (
  chatModel: string | undefined,
): ChatGenerationLivenessPolicy | null =>
  (chatModel?.trim() === "real" ? REAL_MODEL_GENERATION_LIVENESS : null);
