// src/renderer/src/lib/screenSynthesisPrompt.ts
import { extractJSONObject } from './extractJson'
import type { ScreenSegment } from './screenGrouping'

export type ScreenCandidate = { text: string; confidence: number }

// Gemini structured-output schema → forces {candidates:[{text,confidence}]}.
export const SCREEN_RESPONSE_SCHEMA = {
  type: 'object',
  properties: {
    candidates: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          text: { type: 'string' },
          confidence: { type: 'number' }
        },
        required: ['text', 'confidence']
      }
    }
  },
  required: ['candidates']
} as const

export function buildScreenPrompt(segments: ScreenSegment[]): string {
  const blocks = segments
    .map((s, i) => `## Segment ${i + 1} — ${s.app} — ${s.windowTitle}\n${s.text}`)
    .join('\n\n')
  return [
    'You are extracting durable, useful facts about the user from text that appeared on their screen.',
    'Return ONLY atomic facts worth remembering long-term (projects, tools, people, organizations,',
    'interests, ongoing work). One fact per item. Ignore transient UI chrome, menus, ads, and noise.',
    'Each fact gets a confidence in [0,1]. Do NOT invent anything not supported by the text.',
    'Write each fact as a short third-person statement (e.g. "The user is working on the omi-windows port").',
    '',
    'Screen segments:',
    blocks
  ].join('\n')
}

export function parseScreenResponse(raw: string): ScreenCandidate[] {
  try {
    const obj = JSON.parse(extractJSONObject(raw)) as { candidates?: unknown }
    if (!Array.isArray(obj.candidates)) return []
    return obj.candidates
      .map((c) => c as Record<string, unknown>)
      .filter(
        (c) => typeof c.text === 'string' && c.text.trim() !== '' && typeof c.confidence === 'number'
      )
      .map((c) => ({ text: (c.text as string).trim(), confidence: c.confidence as number }))
  } catch {
    return []
  }
}

// Normalize for dedupe: lowercase, collapse whitespace, trim.
export function normalizeForDedupe(text: string): string {
  return text.toLowerCase().replace(/\s+/g, ' ').trim()
}

export function selectWritableCandidates(
  candidates: ScreenCandidate[],
  opts: { threshold: number; cap: number; seen: Set<string> }
): ScreenCandidate[] {
  const out: ScreenCandidate[] = []
  for (const c of candidates) {
    if (out.length >= opts.cap) break
    if (c.confidence < opts.threshold) continue
    const key = normalizeForDedupe(c.text)
    if (opts.seen.has(key)) continue
    opts.seen.add(key)
    out.push(c)
  }
  return out
}
