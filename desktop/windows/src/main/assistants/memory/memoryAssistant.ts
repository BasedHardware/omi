// The Memory assistant — Mac's interval-based memory extractor on Windows. A
// coordinator peer to Focus and Insight, but the simplest of the three: a fixed
// extraction interval, a single-shot vision call (image → structured JSON, NOT a
// tool loop), AT MOST one memory per screenshot, a confidence gate, and a
// local+backend dual-write. It has NO glow and fires NO notification — it just
// records durable facts silently.
//
// analyze() runs the whole pipeline and returns null (side effects inside), like
// Focus and Insight. The coordinator serializes it to one in-flight analysis; a
// monotonic seq guard additionally protects the dev analyzeNow path from writing
// a stale result over a newer coordinator run.
//
// Titles, OCR and memory contents are NEVER logged — only app names and counts.
import { getAppSettings } from '../../appSettings'
import { mayAnalyzeFrame } from '../core/privacy'
import { readFrameImageBase64 } from '../core/frameImage'
import { notificationsActive } from '../core/notify'
import { getBackendSession, getSessionEpoch } from '../core/session'
import { recentMemories } from '../../ipc/db'
import type { AssistantResult, ProactiveAssistant } from '../core/coordinator'
import type { MemoryCategory, RewindFrame } from '../../../shared/types'
import { intervalElapsed } from '../insight/gating'
import { extractMemory } from './gemini'
import { MEMORY_SYSTEM_PROMPT, buildUserPrompt } from './prompt'
import { persistMemory } from './persist'
import type { MemoryExtractionResult } from './models'

const IDENTIFIER = 'memory'

export class MemoryAssistant implements ProactiveAssistant {
  readonly identifier = IDENTIFIER
  readonly displayName = 'Memory'

  /** Monotonic run id; a result whose run is older than the last committed run is
   *  discarded (guards the dev analyzeNow path vs a coordinator run). */
  private seq = 0
  private lastCommittedSeq = -1
  private stopped = false

  /** Master gate. DEVIATION from Mac's `memoryAssistantEnabled &&
   *  memoryNotificationsEnabled`: Mac gates memory extraction on its own
   *  `notificationsEnabled` ("no notification, no Gemini call"). Windows's
   *  equivalent of that master notification switch is the shared
   *  `notificationsActive()` (master on AND frequency > 0 AND not snoozed). Memory
   *  has no glow, so — exactly like Insight — a run whose output can't be delivered
   *  is pure wasted Gemini spend; gating here means default-off extraction until
   *  the user enables notifications, which is faithful to Mac's off-by-default. */
  isEnabled(): boolean {
    if (this.stopped) return false
    return getAppSettings().memoryEnabled && notificationsActive(this.identifier)
  }

  /** Memory's only cadence control: the fixed extraction interval (Mac's
   *  `memoryExtractionInterval`, 600s / 10 min default). */
  private effectiveIntervalMs(): number {
    const min = getAppSettings().memoryExtractionIntervalMin
    return Math.max(1, Number.isFinite(min) ? min : 10) * 60_000
  }

  shouldAnalyze(_frameNumber: number, timeSinceLastAnalysisMs: number): boolean {
    return intervalElapsed(timeSinceLastAnalysisMs, this.effectiveIntervalMs())
  }

  /** The whole pipeline; always returns null (the memory persists inside). */
  async analyze(frame: RewindFrame): Promise<AssistantResult | null> {
    // The builtin + private + denied-context legs of Mac's `isAppExcluded` are
    // already applied by the coordinator (mayAnalyzeFrame) before the frame is
    // offered; Memory's own leg is the USER `memoryExcludedApps` list, checked here.
    if (this.isExcludedApp(frame)) return null
    await this.runPipeline(frame)
    return null
  }

  // Present to satisfy the protocol; all side effects happen inside analyze().
  handleResult(): void {
    /* intentionally empty — the memory is written in analyze(), like Insight */
  }

  stop(): void {
    this.stopped = true
  }

  // --- Internals --------------------------------------------------------------

  /** The user's excluded-apps check: true when this frame's app OR process name is
   *  in `memoryExcludedApps`. Mirrors Focus's isExcludedApp. */
  private isExcludedApp(frame: RewindFrame): boolean {
    const app = (frame.app || '').toLowerCase()
    const proc = (frame.processName || '').toLowerCase()
    const excluded = getAppSettings().memoryExcludedApps.map((a) => a.toLowerCase())
    return excluded.includes(app) || (!!proc && excluded.includes(proc))
  }

  private async runPipeline(frame: RewindFrame): Promise<void> {
    const mySeq = ++this.seq
    console.log(`[memory] analyzing frame app=${frame.app}`)

    const session = getBackendSession()
    if (!session) {
      console.log('[memory] no backend session yet — skipping analysis')
      return
    }
    // Pin the epoch BEFORE the long Gemini call. persist re-checks it right before
    // the write, so a memory formed under this session is never written into the
    // next user's data if the user signs out mid-analysis.
    const sessionEpoch = getSessionEpoch()

    const imageBase64 = await readFrameImageBase64(frame)
    if (!imageBase64) {
      console.log('[memory] frame image missing — skipping')
      return
    }

    let result: MemoryExtractionResult | null
    try {
      // The dedup source: the last ≤20 memories, fed into the prompt so the model
      // does not re-extract them. Reading from the local table (not an in-memory
      // ring like Mac) means the dedup list survives an app restart.
      const recent = recentMemories(20)
      const userPrompt = buildUserPrompt(frame.app || '', recent)
      result = await extractMemory(session, MEMORY_SYSTEM_PROMPT, userPrompt, imageBase64)
    } catch (e) {
      // Errors are just logged (no backoff — the next interval retries).
      console.warn('[memory] extraction error:', e instanceof Error ? e.name : 'Error')
      return
    }

    // Unparseable / empty answer: not an error (models.ts already decided it can't
    // be trusted).
    if (!result) {
      console.log('[memory] no usable extraction from model')
      return
    }

    // Hard cap: Mac only ever takes memories.first, whatever the array holds.
    const mem = result.memories[0]
    if (!mem) {
      console.log('[memory] no memory extracted (0 candidates)')
      return
    }

    // Confidence gate (Mac's 0.7 default), applied before any write.
    const minConfidence = getAppSettings().memoryMinConfidence
    if (mem.confidence < minConfidence) {
      console.log(
        `[memory] filtered: ${Math.round(mem.confidence * 100)}% < ${Math.round(
          minConfidence * 100
        )}%`
      )
      return
    }

    // Stale-result guard: a newer run already committed while this one was in the
    // Gemini call (the dev analyzeNow path can overlap a coordinator run).
    if (mySeq <= this.lastCommittedSeq) {
      console.log('[memory] discarding stale extraction')
      return
    }
    this.lastCommittedSeq = mySeq

    // Map the model's category to our two-value enum (Mac: `.interesting`
    // ? "interesting" : "system"). Anything not 'interesting' is 'system'.
    const category: MemoryCategory = mem.category === 'interesting' ? 'interesting' : 'system'

    persistMemory(
      {
        content: mem.content,
        category,
        // Prefer the model's source_app; fall back to the frame's app when the
        // model left it blank (Mac uses memory.sourceApp directly, but an empty
        // string here would lose real provenance we already have).
        sourceApp: mem.sourceApp || frame.app || '',
        contextSummary: result.contextSummary,
        windowTitle: frame.windowTitle || null,
        confidence: mem.confidence,
        screenshotId: frame.id ?? null,
        createdAt: Date.now()
      },
      sessionEpoch
    )
    console.log(`[memory] extracted category=${category} conf=${Math.round(mem.confidence * 100)}%`)
  }

  /** Dev/QA hook: force one extraction of a given frame, bypassing ONLY the
   *  interval cadence. Every privacy- and safety-relevant gate the coordinator
   *  applies in production is still enforced: the frame privacy gate
   *  (`mayAnalyzeFrame` — incognito / bank / password-manager / login pages), the
   *  user's excluded-apps list, and the session/epoch guard inside runPipeline. */
  async analyzeNowForDev(frame: RewindFrame): Promise<void> {
    if (!mayAnalyzeFrame(frame)) {
      console.log('[memory] analyzeNow skipped — privacy gate')
      return
    }
    if (this.isExcludedApp(frame)) {
      console.log('[memory] analyzeNow skipped — excluded app')
      return
    }
    await this.runPipeline(frame)
  }
}

// --- Runtime singleton -------------------------------------------------------

let singleton: MemoryAssistant | null = null

/** The one Memory assistant. Created on first use so tests can construct their own. */
export function getMemoryAssistant(): MemoryAssistant {
  if (!singleton) singleton = new MemoryAssistant()
  return singleton
}

/** Test-only: drop the singleton. */
export function _resetMemoryAssistant(): void {
  singleton = null
}
