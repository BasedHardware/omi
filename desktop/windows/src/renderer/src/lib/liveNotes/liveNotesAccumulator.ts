// PR8 LiveNotes — word-count-triggered note-generation policy. A faithful port of
// the macOS LiveNotesAccumulator (Desktop/Sources/LiveNotes/LiveNotesAccumulator.swift):
// pure state, no I/O, so it is directly unit-testable. The monitor owns the LLM
// call + persistence; this decides *when* to generate and *what context* to pass.
//
// Trigger is word-count, NOT time: a request fires once `wordThreshold` new
// transcript words have accumulated since the last successful generation. Only
// FRESH words per segment count (segments are re-emitted as they refine around
// pauses — see liveConversation.appendLine's upsert), so a refined segment doesn't
// re-count words it already contributed.

/** A transcript segment reduced to what the accumulator needs. The monitor maps
 *  TranscriptLine → this, substituting a positional key for id-less lines. */
export type AccumulatorSegment = { id: string; text: string }

export type LiveNotesGenerationRequest = {
  recentText: string
  existingNotesText: string
  segmentStartOrder: number
  segmentEndOrder: number
}

// Mac defaults (LiveNotesAccumulator.swift:23-25). Kept as constructor options so
// tests can drive smaller thresholds without waiting for 50 words.
export const DEFAULT_WORD_THRESHOLD = 50
export const DEFAULT_MAX_WORD_BUFFER = 500
export const DEFAULT_MAX_EXISTING_NOTES_CONTEXT = 20

function words(text: string): string[] {
  // Whitespace-run split (Mac splits on " "); dropping empties keeps the count
  // right across multiple spaces / newlines (injected lines carry newlines).
  return text.trim().length ? text.trim().split(/\s+/) : []
}

export class LiveNotesAccumulator {
  readonly wordThreshold: number
  readonly maxWordBufferSize: number
  readonly maxExistingNotesContext: number

  private wordBuffer: string[] = []
  private existingNotesContext: string[] = []
  private currentSegmentOrder = 0
  private processedSegmentWordCounts = new Map<string, number>()
  private wordsSinceLastGeneration = 0

  constructor(opts?: {
    wordThreshold?: number
    maxWordBufferSize?: number
    maxExistingNotesContext?: number
  }) {
    this.wordThreshold = opts?.wordThreshold ?? DEFAULT_WORD_THRESHOLD
    this.maxWordBufferSize = opts?.maxWordBufferSize ?? DEFAULT_MAX_WORD_BUFFER
    this.maxExistingNotesContext =
      opts?.maxExistingNotesContext ?? DEFAULT_MAX_EXISTING_NOTES_CONTEXT
  }

  /** Segment count covered so far (Mac's currentSegmentOrder) — used to stamp a
   *  manual note's segmentStartOrder. */
  get segmentOrder(): number {
    return this.currentSegmentOrder
  }

  reset(): void {
    this.wordBuffer = []
    this.existingNotesContext = []
    this.currentSegmentOrder = 0
    this.processedSegmentWordCounts = new Map()
    this.wordsSinceLastGeneration = 0
  }

  /** Replace the existing-notes context (e.g. after loading a session's notes from
   *  DB, or after an edit/delete rebuilds the list). */
  seedExistingNotes(notes: string[]): void {
    this.existingNotesContext = this.trimmedContext(notes)
  }

  /** Append one note to the context (a new AI or manual note), trimming to cap. */
  appendExistingNote(note: string): void {
    this.existingNotesContext.push(note)
    this.existingNotesContext = this.trimmedContext(this.existingNotesContext)
  }

  /** Feed the latest transcript segments. Returns a generation request iff enough
   *  NEW words have arrived and no generation is already in flight (single-flight
   *  is the caller's boolean, mirroring Mac). */
  handleSegmentsUpdate(
    segments: AccumulatorSegment[],
    isGenerating: boolean
  ): LiveNotesGenerationRequest | null {
    this.currentSegmentOrder = segments.length

    // Forget segments that are no longer present (a new conversation cleared them),
    // so their word counts don't suppress fresh words that reuse an id.
    const currentIds = new Set(segments.map((s) => s.id))
    for (const id of [...this.processedSegmentWordCounts.keys()]) {
      if (!currentIds.has(id)) this.processedSegmentWordCounts.delete(id)
    }

    const newWords: string[] = []
    for (const segment of segments) {
      const w = words(segment.text)
      const processed = this.processedSegmentWordCounts.get(segment.id) ?? 0
      this.processedSegmentWordCounts.set(segment.id, w.length)
      if (w.length > processed) newWords.push(...w.slice(processed))
    }
    if (newWords.length === 0) return null

    this.wordBuffer.push(...newWords)
    this.wordsSinceLastGeneration += newWords.length
    this.trimWordBuffer()

    if (this.wordsSinceLastGeneration < this.wordThreshold || isGenerating) return null

    return {
      recentText: this.wordBuffer.slice(-this.wordThreshold).join(' '),
      existingNotesText: this.existingNotesText(),
      segmentStartOrder: Math.max(0, this.currentSegmentOrder - 3),
      segmentEndOrder: this.currentSegmentOrder
    }
  }

  /** After a note is stored: decrement the counter by exactly the threshold (NOT
   *  reset to 0, so a burst past 50 keeps the remainder toward the next note) and
   *  add the note to context so the next prompt avoids repeating it. */
  markGenerationSucceeded(noteText: string): void {
    this.wordsSinceLastGeneration = Math.max(0, this.wordsSinceLastGeneration - this.wordThreshold)
    this.appendExistingNote(noteText)
  }

  private trimWordBuffer(): void {
    if (this.wordBuffer.length > this.maxWordBufferSize) {
      this.wordBuffer = this.wordBuffer.slice(this.wordBuffer.length - this.maxWordBufferSize)
    }
  }

  private trimmedContext(notes: string[]): string[] {
    return notes.length > this.maxExistingNotesContext
      ? notes.slice(notes.length - this.maxExistingNotesContext)
      : [...notes]
  }

  private existingNotesText(): string {
    if (this.existingNotesContext.length === 0) return 'No existing notes yet.'
    return 'Existing notes:\n' + this.existingNotesContext.map((n) => `- ${n}`).join('\n')
  }
}
