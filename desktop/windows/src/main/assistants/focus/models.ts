// The Focus assistant's contract with Gemini: the response schema it asks for,
// and the parse/validation of what comes back. Pure — no network, no Electron.
//
// The schema is Mac's, field for field (`FocusAssistant.swift` analyzeScreenshot):
// `message` is deliberately OPTIONAL while the other three are required, because
// a coaching line is a nicety and a status is not — a response missing `message`
// is still a usable judgment, a response missing `status` is nothing at all.
import type { FocusSessionStatus } from '../../../shared/types'

/** One Gemini judgment of one frame. */
export type ScreenAnalysis = {
  status: FocusSessionStatus
  appOrSite: string
  description: string
  /** Coaching line, ≤100 chars (the notification banner's budget). Absent is legal. */
  message: string | null
}

/** Gemini `generationConfig.responseSchema` — exactly Mac's shape. */
export const FOCUS_RESPONSE_SCHEMA = {
  type: 'object',
  properties: {
    status: {
      type: 'string',
      enum: ['focused', 'distracted'],
      description: 'Whether the user is focused or distracted'
    },
    app_or_site: { type: 'string', description: 'The app or website visible' },
    description: { type: 'string', description: "Brief description of what's on screen" },
    message: { type: 'string', description: 'Coaching message' }
  },
  required: ['status', 'app_or_site', 'description']
} as const

function str(v: unknown): string {
  return typeof v === 'string' ? v.trim() : ''
}

/**
 * Parse Gemini's JSON text into a ScreenAnalysis. Returns null on anything we
 * cannot trust — a structured-output model still occasionally returns prose, an
 * empty part, or a status outside the enum, and a bad parse must degrade to "no
 * judgment this frame" rather than throw (which would spend an error-backoff
 * cycle) or coerce (which would invent a verdict the model never made).
 */
export function parseScreenAnalysis(text: string): ScreenAnalysis | null {
  let raw: unknown
  try {
    raw = JSON.parse(text)
  } catch {
    return null
  }
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return null
  const o = raw as Record<string, unknown>

  const status = str(o.status)
  if (status !== 'focused' && status !== 'distracted') return null

  const message = str(o.message)
  return {
    status,
    appOrSite: str(o.app_or_site),
    description: str(o.description),
    // '' and absent are the same thing to every caller (the message gates the
    // notification), so normalize both to null rather than carrying two empties.
    message: message.length > 0 ? message : null
  }
}
