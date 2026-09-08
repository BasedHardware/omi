// src/renderer/src/lib/screenSynthesis.ts
import { omiApi } from './apiClient'
import { generate } from './geminiClient'
import { redact, isPrivateWindow, isDeniedContext } from './screenRedact'
import { groupFrames, budgetSegments } from './screenGrouping'
import {
  buildScreenPrompt,
  parseScreenResponse,
  selectWritableCandidates,
  normalizeForDedupe,
  SCREEN_RESPONSE_SCHEMA
} from './screenSynthesisPrompt'
import { SCREEN_TAG } from './screenTag'
import { maybeBuildLocalGraph } from './kgSynthesis'
import type { ScreenFrameLite } from '../../../shared/types'

const MODEL = (import.meta.env.VITE_GEMINI_MODEL as string) || 'gemini-2.5-flash'
const INTERVAL_MS = 10 * 60 * 1000 // 10 min — matches macOS MemoryExtraction extractionInterval
const PROMPT_BUDGET_CHARS = 12_000
const CONFIDENCE_THRESHOLD = 0.7
const PER_RUN_CAP = 10

// Dedupe screen facts created this session (defense vs. re-emitting the same fact
// across adjacent batches; the confidence gate + watermark handle the rest).
const seenThisSession = new Set<string>()
let running = false
let scheduled = false

function filterFrames(frames: ScreenFrameLite[]): ScreenFrameLite[] {
  return frames.filter((f) => {
    if (isPrivateWindow(f.windowTitle)) return false
    if (isDeniedContext({ app: f.app, windowTitle: f.windowTitle, processName: f.processName }))
      return false
    return true
  })
}

// One synthesis pass. Best-effort: any failure is swallowed and the watermark is
// NOT advanced, so the next run retries the same frames. Returns memories written.
export async function runScreenSynthesisOnce(): Promise<number> {
  if (running) return 0
  running = true
  try {
    const state = await window.omi.screenSynthGetState()
    if (!state.enabled) return 0

    const frames = await window.omi.screenSynthFramesSince()
    if (frames.length === 0) return 0
    const maxTs = frames[frames.length - 1].ts

    const allowed = filterFrames(frames)
    if (allowed.length === 0) {
      // Nothing synthesizable, but these frames are handled — advance past them.
      await window.omi.screenSynthAdvanceWatermark(maxTs)
      return 0
    }

    // Redact on-device BEFORE building the prompt (nothing un-redacted leaves).
    const redacted = allowed.map((f) => ({ ...f, ocrText: redact(f.ocrText) }))
    const segments = budgetSegments(groupFrames(redacted), PROMPT_BUDGET_CHARS)
    if (segments.length === 0) {
      await window.omi.screenSynthAdvanceWatermark(maxTs)
      return 0
    }

    const raw = await generate({
      model: MODEL,
      parts: [{ text: buildScreenPrompt(segments) }],
      responseSchema: SCREEN_RESPONSE_SCHEMA as unknown as Record<string, unknown>
    })
    const candidates = parseScreenResponse(raw)
    const writable = selectWritableCandidates(candidates, {
      threshold: CONFIDENCE_THRESHOLD,
      cap: PER_RUN_CAP,
      seen: seenThisSession
    })

    let written = 0
    for (const c of writable) {
      try {
        await omiApi.post('/v3/memories', { content: c.text, tags: [SCREEN_TAG] })
        written++
      } catch {
        // On a write failure, roll back its dedupe entry so a retry can write it.
        seenThisSession.delete(normalizeForDedupe(c.text))
      }
    }

    // Advance only after a successful batch (writes attempted).
    await window.omi.screenSynthAdvanceWatermark(maxTs)
    await window.omi.screenSynthRecordRun({ lastRunAt: Date.now(), lastCount: written })
    if (written > 0) void maybeBuildLocalGraph() // debounced inside (staleness-gated)
    return written
  } catch (e) {
    console.warn('[screen-synth] run failed', e)
    return 0
  } finally {
    running = false
  }
}

// Start the 15-min scheduler once (idempotent). Gated on the enabled flag at run
// time, so toggling the setting takes effect on the next tick without a restart.
export function maybeStartScreenSynthesis(): void {
  if (scheduled) return
  scheduled = true
  // First pass shortly after launch, then on the interval.
  window.setTimeout(() => void runScreenSynthesisOnce(), 30_000)
  window.setInterval(() => void runScreenSynthesisOnce(), INTERVAL_MS)
}
