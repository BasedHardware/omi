// Push-to-talk vocabulary boosting (Track 2 A2).
//
// Gathers best-effort "what is the user looking at / talking about" terms and
// ships them to /v2/voice-message/transcribe as the `keywords` hint so the STT
// provider biases toward on-screen proper nouns, product names, and people —
// exactly the words a generic model mangles. Faithful port of macOS
// PTTContextVocabularyProvider (KeywordCollector shape, caps, stop-words), minus
// the on-device pieces Windows doesn't have.
//
// Three sources, all optional and non-throwing (a dead source contributes
// nothing; it never breaks a turn):
//   1. user-configured vocabulary — no Windows machinery yet (the custom-
//      vocabulary control in TranscriptionTab is deliberately unbuilt; vocabulary
//      lives only in the backend transcription-preferences PATCH), so this is
//      currently empty. Kept as an explicit slot so it lights up for free when a
//      local pref lands.
//   2. the active screen's OCR text (window.omi.screenReadText).
//   3. recent-activity OCR from the last 120s of rewind frames.
//
// Collection is capped at PTT_VOCAB_MAX_COLLECTED (100); the wire pass
// (pttKeywordsParam) prepends the brand terms, hard-caps at PTT_VOCAB_MAX_WIRE
// (40), and comma-joins for the query param.
import type { RewindFrame } from '../../../../shared/types'
import {
  PTT_VOCAB_CONSUME_TIMEOUT_MS,
  PTT_VOCAB_FRAME_OCR_CHARS,
  PTT_VOCAB_IMMEDIATE_OCR_CHARS,
  PTT_VOCAB_LOOKBACK_MS,
  PTT_VOCAB_MAX_COLLECTED,
  PTT_VOCAB_MAX_FRAMES,
  PTT_VOCAB_MAX_WIRE,
  PTT_VOCAB_OCR_TIMEOUT_MS,
  PTT_VOCAB_REWIND_TIMEOUT_MS
} from './constants'

// The two preload calls this module reaches for, typed loosely so a bridge that
// predates them (or a test fake) is a clean no-op rather than a crash.
type ContextBridge = {
  screenReadText?: () => Promise<string>
  rewindFrames?: (from: number, to: number) => Promise<RewindFrame[]>
}

function contextBridge(): ContextBridge | null {
  if (typeof window === 'undefined') return null
  return (window.omi as ContextBridge | undefined) ?? null
}

function withTimeout<T>(work: Promise<T>, ms: number, fallback: T): Promise<T> {
  return Promise.race([work, new Promise<T>((resolve) => setTimeout(() => resolve(fallback), ms))])
}

async function immediateScreenText(): Promise<string | null> {
  const read = contextBridge()?.screenReadText
  if (typeof read !== 'function') return null
  try {
    const text = await withTimeout(read(), PTT_VOCAB_OCR_TIMEOUT_MS, '')
    const trimmed = (text ?? '').trim()
    return trimmed || null
  } catch {
    return null
  }
}

async function recentActivityFrames(now: number): Promise<RewindFrame[]> {
  const load = contextBridge()?.rewindFrames
  if (typeof load !== 'function') return []
  try {
    const frames = await withTimeout(
      load(now - PTT_VOCAB_LOOKBACK_MS, now + 2000),
      PTT_VOCAB_REWIND_TIMEOUT_MS,
      [] as RewindFrame[]
    )
    return (frames ?? []).slice(0, PTT_VOCAB_MAX_FRAMES)
  } catch {
    return []
  }
}

/**
 * Gather up to PTT_VOCAB_MAX_COLLECTED transcription-boost terms from the active
 * screen and recent activity. Never throws — every source failure is swallowed
 * and simply contributes nothing (so the PTT turn always proceeds).
 */
export async function collectPttKeywords(now: number = Date.now()): Promise<string[]> {
  try {
    const collector = new KeywordCollector(PTT_VOCAB_MAX_COLLECTED)

    // Source 1: user-configured vocabulary — no Windows preference exists yet
    // (see TranscriptionTab), so nothing to add today.

    // Sources 2 + 3 run in parallel (macOS `async let` shape).
    const [immediate, frames] = await Promise.all([
      immediateScreenText(),
      recentActivityFrames(now)
    ])

    // Source 2: the active screen right now.
    if (immediate) {
      const clipped = immediate.slice(0, PTT_VOCAB_IMMEDIATE_OCR_CHARS)
      collector.addExtractedTerms(clipped)
      collector.addVisibleTerms(clipped)
    }

    // Source 3: recent-activity frames (app name + window title + OCR).
    for (const frame of frames) {
      collector.add(frame.app)
      if (frame.windowTitle) {
        collector.add(frame.windowTitle)
        collector.addExtractedTerms(frame.windowTitle)
      }
      if (frame.ocrText)
        collector.addExtractedTerms(frame.ocrText.slice(0, PTT_VOCAB_FRAME_OCR_CHARS))
    }

    return collector.values
  } catch {
    return []
  }
}

// --- Hold-start collection cache (A2 latency hiding) ---------------------------
//
// Keyword collection runs bounded OCR (up to PTT_VOCAB_OCR_TIMEOUT_MS). Running
// it inside batchTranscribe — on key-UP, the gesture-critical path — would tax
// every turn's latency by that ceiling. macOS instead collects at key-DOWN so
// the work overlaps the hold and is free by the time the user releases. We do the
// same: startPttKeywordCollection() fires at hold-start and stashes the in-flight
// promise here; batchTranscribe consumes it with a short bound. On a normal hold
// (longer than the OCR ceiling) the promise is already resolved at key-up, so the
// consume returns instantly; a very short hold degrades to the brand prepend.
let inFlightCollection: Promise<string[]> | null = null

/**
 * Kick off this turn's keyword collection (call at hold-start). Overwrites any
 * prior turn's in-flight collection, so a new hold never reuses stale terms.
 * Never throws — collectPttKeywords swallows every source failure.
 */
export function startPttKeywordCollection(now: number = Date.now()): void {
  inFlightCollection = collectPttKeywords(now)
}

/**
 * Consume this turn's collected keywords, bounded by `timeoutMs` so a short hold
 * that released before collection finished never stalls the transcribe POST.
 * Returns [] (⇒ brand prepend only from pttKeywordsParam) when nothing was
 * collected or the collection is not ready yet. One-shot: clears the cache so a
 * later transcribe in the same session can't reuse this turn's terms.
 */
export async function consumePttKeywords(
  timeoutMs: number = PTT_VOCAB_CONSUME_TIMEOUT_MS
): Promise<string[]> {
  const pending = inFlightCollection
  inFlightCollection = null
  if (!pending) return []
  // Non-throwing at the boundary: batchTranscribe awaits this with no guard of
  // its own, so vocabulary must never break a turn even if a source starts
  // rejecting. (collectPttKeywords already swallows failures; this is a backstop.)
  return withTimeout(pending, timeoutMs, [] as string[]).catch(() => [] as string[])
}

/** Test-only: drop any cached in-flight collection. */
export function __resetPttKeywordsForTests(): void {
  inFlightCollection = null
}

/**
 * Wire pass: assemble the comma-separated `keywords` query-param value. Always
 * prepends the brand terms ("Omi", "OMI"), re-enforces the 2–80 char / no-comma
 * / case-insensitive-dedup contract, and hard-caps the whole list at
 * PTT_VOCAB_MAX_WIRE. Pure — safe to unit-test in isolation.
 */
export function pttKeywordsParam(terms: string[]): string {
  const out: string[] = ['Omi', 'OMI']
  const seen = new Set<string>(['omi']) // both brand variants share one dedup key
  for (const raw of terms) {
    if (out.length >= PTT_VOCAB_MAX_WIRE) break
    const term = raw.trim()
    if (term.length < 2 || term.length > 80) continue
    if (term.includes(',')) continue // a literal comma would corrupt the param
    const key = term.toLowerCase()
    if (seen.has(key)) continue
    seen.add(key)
    out.push(term)
  }
  return out.join(',')
}

/**
 * Ported from macOS KeywordCollector: a dedup + stop-word + length gate, plus
 * proper-noun / acronym / visible-word extraction from OCR text.
 */
class KeywordCollector {
  // macOS stop-word set, verbatim — common chat/UI chrome that is never a useful
  // transcription hint.
  static readonly stopWords: ReadonlySet<string> = new Set([
    'about',
    'after',
    'again',
    'all',
    'also',
    'and',
    'app',
    'are',
    'ask',
    'back',
    'browser',
    'but',
    'can',
    'chat',
    'code',
    'done',
    'each',
    'for',
    'from',
    'has',
    'have',
    'here',
    'into',
    'just',
    'like',
    'more',
    'hello',
    'hi',
    'next',
    'not',
    'now',
    'okay',
    'open',
    'orange',
    'question',
    'reply',
    'running',
    'said',
    'say',
    'send',
    'sent',
    'show',
    'some',
    'task',
    'tell',
    'test',
    'text',
    'that',
    'the',
    'this',
    'thread',
    'time',
    'to',
    'too',
    'two',
    'use',
    'user',
    'voice',
    'was',
    'what',
    'when',
    'with',
    'you',
    'your'
  ])

  private readonly seen = new Set<string>()
  readonly values: string[] = []

  constructor(private readonly limit: number) {}

  add(raw: string): void {
    if (this.values.length >= this.limit) return
    const term = raw.trim().replace(/^[.,;:()[\]{}<>"']+|[.,;:()[\]{}<>"']+$/g, '')
    if (term.length < 2 || term.length > 80) return
    if (!/[A-Za-z]/.test(term)) return
    const key = term.toLowerCase()
    if (KeywordCollector.stopWords.has(key) || this.seen.has(key)) return
    this.seen.add(key)
    this.values.push(term)
  }

  /** Proper nouns (1–3 capitalized words) and acronyms. */
  addExtractedTerms(text: string): void {
    const patterns = [
      /\b[A-Z][A-Za-z'-]{2,}(?:\s+[A-Z][A-Za-z'-]{2,}){1,2}\b/g,
      /\b[A-Z][A-Za-z'-]{2,}\b/g,
      /\b[A-Z]{2,8}\b/g
    ]
    for (const pattern of patterns) {
      for (const match of text.matchAll(pattern)) {
        this.add(match[0])
        if (this.values.length >= this.limit) return
      }
    }
  }

  /** Every visible word (2–32 chars) — lower-priority fill after proper nouns. */
  addVisibleTerms(text: string): void {
    for (const match of text.matchAll(/\b[A-Za-z][A-Za-z'-]{1,31}\b/g)) {
      this.add(match[0])
      if (this.values.length >= this.limit) return
    }
  }
}
