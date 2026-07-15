// src/renderer/src/lib/insightEngine.ts
//
// RETIRED (Track 3 P4): the Insight extraction loop moved to the main process
// (src/main/assistants/insight/*) as a faithful port of macOS's two-phase
// tool-calling pipeline, hosted by the proactive-assistant coordinator. Exactly
// ONE Insight engine now runs — the main one — so there is never a duplicate
// toast. The renderer-side single-shot summarize+schema engine that used to live
// here (runInsightOnce) is gone; its pure helpers (insightPrompt / insightGate /
// insightActivity) remain importable but unused.
//
// This bootstrap survives ONLY to start the two renderer→main session relays that
// the main-process services need (they are inert without a Firebase token): the
// AI-profile host and the Rewind embedding indexer. Both are idempotent and
// app-session-lived. The function name is unchanged so Home.tsx's single caller
// (and its test mock) keep working.
import { startAiProfileHost } from './aiProfileHost'
import { startRewindEmbedHost } from './rewindEmbedHost'

let started = false

export function maybeStartInsightEngine(): void {
  if (started) return
  started = true
  startAiProfileHost()
  startRewindEmbedHost()
}
