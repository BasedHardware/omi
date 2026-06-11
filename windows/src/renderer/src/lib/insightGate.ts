// src/renderer/src/lib/insightGate.ts
import type { InsightPayload } from '../../../shared/types'

const norm = (s: string): string => s.toLowerCase().replace(/\s+/g, ' ').trim()

export function selectInsight(
  candidate: InsightPayload | null,
  opts: { threshold: number; recentHeadlines: string[] }
): InsightPayload | null {
  if (!candidate) return null
  if (candidate.confidence < opts.threshold) return null
  const key = norm(candidate.headline)
  if (opts.recentHeadlines.map(norm).includes(key)) return null
  return candidate
}
