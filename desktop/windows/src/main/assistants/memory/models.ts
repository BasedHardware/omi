// The Memory assistant's contract with Gemini: the response schema it asks for,
// and the parse/validation of what comes back. Pure — no network, no Electron.
//
// Field names/types are Mac's, verbatim (`MemoryExtractionModels.swift` +
// `MemoryAssistant.swift`'s `responseSchema`): `has_new_memory`, `memories[]`
// ({content, category, source_app, confidence}), `context_summary`,
// `current_activity`. Only `memories[0]` is ever used downstream (Mac's hard cap
// of 1), but the whole shape is parsed so a malformed field degrades cleanly.
import type { MemoryCategory } from '../../../shared/types'

/** One candidate memory the model proposes. */
export type ExtractedMemory = {
  content: string
  category: MemoryCategory
  sourceApp: string
  /** 0.0–1.0. Load-bearing: the caller drops the memory below the confidence gate. */
  confidence: number
}

/** One Gemini extraction pass over one frame. */
export type MemoryExtractionResult = {
  hasNewMemory: boolean
  memories: ExtractedMemory[]
  contextSummary: string
  currentActivity: string
}

/** Gemini `generationConfig.responseSchema` — exactly Mac's shape. */
export const MEMORY_RESPONSE_SCHEMA = {
  type: 'object',
  properties: {
    has_new_memory: { type: 'boolean', description: 'True if new memories were found' },
    memories: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          content: { type: 'string', description: 'The memory content (max 15 words)' },
          category: {
            type: 'string',
            enum: ['system', 'interesting'],
            description: 'Memory category'
          },
          source_app: { type: 'string', description: 'App where memory was found' },
          confidence: { type: 'number', description: 'Confidence score 0.0-1.0' }
        },
        required: ['content', 'category', 'source_app', 'confidence']
      }
    },
    context_summary: { type: 'string', description: 'Brief summary of what user is looking at' },
    current_activity: { type: 'string', description: "High-level description of user's activity" }
  },
  required: ['has_new_memory', 'memories', 'context_summary', 'current_activity']
} as const

function str(v: unknown): string {
  return typeof v === 'string' ? v.trim() : ''
}

/** Parse one candidate memory, or null if it can't be trusted. A bad `category`
 *  is dropped, NOT coerced to 'system' — coercing would invent a classification
 *  the model never made. Missing/NaN confidence is a drop (the gate needs it). */
function parseMemory(v: unknown): ExtractedMemory | null {
  if (!v || typeof v !== 'object' || Array.isArray(v)) return null
  const o = v as Record<string, unknown>
  const content = str(o.content)
  if (!content) return null
  const category = str(o.category)
  if (category !== 'system' && category !== 'interesting') return null
  const confidence = o.confidence
  if (typeof confidence !== 'number' || !Number.isFinite(confidence)) return null
  return { content, category, sourceApp: str(o.source_app), confidence }
}

/**
 * Parse Gemini's JSON text into a MemoryExtractionResult. Returns null on anything
 * we cannot trust at the top level (prose, an empty part, a non-object) — a bad
 * parse must degrade to "no extraction this frame" rather than throw or coerce.
 *
 * Malformed ENTRIES inside `memories` are filtered out (not fatal): the array can
 * come back with a bad-enum item while the rest is fine, so a single junk entry
 * yields an empty `memories`, never a null result.
 */
export function parseMemoryExtraction(text: string): MemoryExtractionResult | null {
  let raw: unknown
  try {
    raw = JSON.parse(text)
  } catch {
    return null
  }
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return null
  const o = raw as Record<string, unknown>

  const memories = Array.isArray(o.memories)
    ? o.memories.map(parseMemory).filter((m): m is ExtractedMemory => m !== null)
    : []

  return {
    hasNewMemory: o.has_new_memory === true,
    memories,
    contextSummary: str(o.context_summary),
    currentActivity: str(o.current_activity)
  }
}
