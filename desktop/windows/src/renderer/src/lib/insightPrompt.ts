// src/renderer/src/lib/insightPrompt.ts
import { extractJSONObject } from './extractJson'
import type { InsightPayload, InsightCategory } from '../../../shared/types'

const CATEGORIES: InsightCategory[] = [
  'productivity', 'communication', 'learning', 'health', 'other'
]

export const INSIGHT_RESPONSE_SCHEMA = {
  type: 'object',
  properties: {
    has_insight: { type: 'boolean' },
    insight: {
      type: 'object',
      properties: {
        headline: { type: 'string' },
        advice: { type: 'string' },
        reasoning: { type: 'string' },
        category: { type: 'string' },
        source_app: { type: 'string' },
        confidence: { type: 'number' }
      }
    }
  },
  required: ['has_insight']
} as const

export function buildInsightPrompt(activitySummary: string, recentHeadlines: string[]): string {
  const recent = recentHeadlines.length
    ? `\nAlready-given insights (do NOT repeat these):\n- ${recentHeadlines.join('\n- ')}`
    : ''
  return [
    'You look at a summary of what the user has been doing on screen (from OCR) and decide if there',
    'is ONE genuinely useful, non-obvious insight or piece of advice worth interrupting them for.',
    'Most of the time there is NOT — only surface something clearly helpful.',
    'If you have one, return has_insight=true with: headline (<=5 words), advice (1-2 sentences,',
    '<=100 chars), reasoning, category (productivity|communication|learning|health|other),',
    'source_app, confidence (0-1). Otherwise has_insight=false. Do not invent anything not in the text.',
    recent,
    '',
    'Recent screen activity:',
    activitySummary
  ].join('\n')
}

export function parseInsightResponse(raw: string): InsightPayload | null {
  try {
    const obj = JSON.parse(extractJSONObject(raw)) as {
      has_insight?: boolean
      insight?: Record<string, unknown>
    }
    if (!obj.has_insight || !obj.insight) return null
    const i = obj.insight
    if (typeof i.headline !== 'string' || typeof i.advice !== 'string') return null
    if (typeof i.confidence !== 'number') return null
    const cat = i.category as InsightCategory
    return {
      headline: i.headline.trim(),
      advice: i.advice.trim(),
      reasoning: typeof i.reasoning === 'string' ? i.reasoning : '',
      category: CATEGORIES.includes(cat) ? cat : 'other',
      sourceApp: typeof i.source_app === 'string' ? i.source_app : '',
      confidence: i.confidence
    }
  } catch {
    return null
  }
}
