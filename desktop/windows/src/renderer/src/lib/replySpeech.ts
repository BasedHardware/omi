type SpeechWindow = {
  speechSynthesis?: SpeechSynthesis
  SpeechSynthesisUtterance?: new (text: string) => SpeechSynthesisUtterance
}

type BoundaryLimits = {
  min: number
  preferred: number
  emergency: number
}

const FIRST_CHUNK: BoundaryLimits = { min: 40, preferred: 120, emergency: 200 }
const FOLLOWUP_CHUNK: BoundaryLimits = { min: 320, preferred: 520, emergency: 800 }

const SENTENCE_END = new Set(['.', '!', '?', '\n', '\r'])
const CLAUSE_END = new Set([',', ';', ':'])

export type ReplySpeechPlayer = {
  startFiller: () => void
  speak: (text: string) => boolean
  cancel: () => void
}

export type ReplySpeechOptions = {
  getWindow?: () => SpeechWindow | undefined
  fillerText?: string
}

export function findReplySpeechBoundary(
  text: string,
  opts: { final?: boolean; first?: boolean } = {}
): number | null {
  if (!text.trim()) return null
  if (opts.final) return text.length

  const limits = opts.first === false ? FOLLOWUP_CHUNK : FIRST_CHUNK
  if (text.length < limits.min) return null

  const sentence = findLastBoundary(text, limits.min, text.length, (ch) => SENTENCE_END.has(ch))
  if (sentence !== null) return sentence

  if (text.length >= limits.preferred) {
    const clause = findLastBoundary(text, limits.min, text.length, (ch) => CLAUSE_END.has(ch))
    if (clause !== null) return clause

    const whitespace = findLastBoundary(text, limits.min, text.length, (ch) => /\s/.test(ch))
    if (whitespace !== null) return whitespace
  }

  if (text.length >= limits.emergency) {
    const cut = Math.min(text.length, limits.emergency)
    const whitespace = findLastBoundary(text, limits.min, cut, (ch) => /\s/.test(ch))
    return whitespace ?? cut
  }

  return null
}

export function createWebSpeechReplyPlayer(opts: ReplySpeechOptions = {}): ReplySpeechPlayer {
  const getWindow = opts.getWindow ?? (() => (typeof window === 'undefined' ? undefined : window))
  const fillerText = opts.fillerText ?? 'One moment.'
  let fillerActive = false

  const resolve = (): {
    synth: SpeechSynthesis
    Utterance: new (text: string) => SpeechSynthesisUtterance
  } | null => {
    const w = getWindow()
    if (!w?.speechSynthesis || !w.SpeechSynthesisUtterance) return null
    return { synth: w.speechSynthesis, Utterance: w.SpeechSynthesisUtterance }
  }

  const speak = (text: string): boolean => {
    const clean = normalizeSpeechText(text)
    if (!clean) return false
    const speech = resolve()
    if (!speech) return false
    if (fillerActive) {
      speech.synth.cancel()
      fillerActive = false
    }
    speech.synth.speak(new speech.Utterance(clean))
    return true
  }

  return {
    startFiller: () => {
      const speech = resolve()
      if (!speech) return
      speech.synth.cancel()
      fillerActive = true
      speech.synth.speak(new speech.Utterance(fillerText))
    },
    speak,
    cancel: () => {
      const speech = resolve()
      if (speech) speech.synth.cancel()
      fillerActive = false
    }
  }
}

function findLastBoundary(
  text: string,
  min: number,
  max: number,
  matches: (ch: string) => boolean
): number | null {
  const end = Math.min(max, text.length)
  for (let i = end - 1; i >= min - 1; i--) {
    if (matches(text[i])) return i + 1
  }
  return null
}

function normalizeSpeechText(text: string): string {
  return text.replace(/\s+/g, ' ').trim()
}
