/**
 * Workstream pooling — pure port of macOS ContextWorkstreamPooling: the tag
 * sanitizer, the live-tag resolution rule, pooled-fact selection/scoring, and
 * the non-citable prompt sections. All flag-gated on Windows exactly as mac
 * gates them off in production.
 */

import { isScaffoldingStatement } from '../../ipc/contextBucketStore'

export const WORKSTREAM_TAG_MAX_LENGTH = 32
export const POOL_WORTHINESS_FLOOR = 0.3
export const POOL_MAX_ITEMS = 8
export const POOL_MAX_PER_BUCKET = 3
export const POOL_RECENCY_HALF_LIFE_HOURS = 6.0
export const RECENT_CONTEXT_WORTHINESS_FLOOR = 0.6
export const RECENT_CONTEXT_MAX_ITEMS = 3
export const RECENT_CONTEXT_MAX_PER_BUCKET = 1
export const BUCKET_MAJORITY_SHARE = 0.8
export const BUCKET_MAJORITY_MINIMUM_FACTS = 3

/** Kebab-case sanitize: 2-32 chars of [a-z0-9-]; `unknown` is abstention. */
export function sanitizeWorkstreamTag(raw: string): string | null {
  let tag = raw.trim().toLowerCase()
  tag = tag.replace(/[\s_]+/g, '-')
  tag = tag.replace(/[^a-z0-9-]/g, '')
  tag = tag.replace(/-{2,}/g, '-')
  tag = tag.replace(/^-+|-+$/g, '')
  if (tag.length < 2 || tag.length > WORKSTREAM_TAG_MAX_LENGTH) return null
  if (tag === 'unknown') return null
  return tag
}

/** Live tag: any own-visit tag wins (max by count then key); otherwise the
 *  bucket-majority tag stands in only at >=3 tagged facts and >=80% share. */
export function liveTag(
  own: ReadonlyMap<string, number>,
  bucket: ReadonlyMap<string, number>
): string | null {
  const maxByCountThenKey = (counts: ReadonlyMap<string, number>): string | null => {
    let best: string | null = null
    let bestCount = 0
    for (const [tag, count] of counts) {
      if (count > bestCount || (count === bestCount && best !== null && tag > best)) {
        best = tag
        bestCount = count
      }
    }
    return best
  }
  const ownBest = maxByCountThenKey(own)
  if (ownBest !== null) return ownBest

  let total = 0
  for (const count of bucket.values()) total += count
  if (total < BUCKET_MAJORITY_MINIMUM_FACTS) return null
  const bucketBest = maxByCountThenKey(bucket)
  if (bucketBest === null) return null
  if ((bucket.get(bucketBest) ?? 0) < BUCKET_MAJORITY_SHARE * total) return null
  return bucketBest
}

export interface PoolFact {
  factID: string
  bucketID: string
  appName: string
  statement: string
  notifyWorthiness: number
  createdAt: number
}

/** Score `worthiness + 0.5^(ageHours/6)`, sorted descending with factID
 *  tie-break; per-bucket then total caps. */
export function selectPooledFacts(
  facts: readonly PoolFact[],
  now: number,
  opts: {
    worthinessFloor?: number
    maxItems?: number
    maxPerBucket?: number
    createdAfter?: number
  } = {}
): PoolFact[] {
  const floor = opts.worthinessFloor ?? POOL_WORTHINESS_FLOOR
  const maxItems = opts.maxItems ?? POOL_MAX_ITEMS
  const maxPerBucket = opts.maxPerBucket ?? POOL_MAX_PER_BUCKET

  const scored = facts
    .filter((f) => f.notifyWorthiness >= floor)
    .filter((f) => !isScaffoldingStatement(f.statement))
    .filter((f) => opts.createdAfter === undefined || f.createdAt >= opts.createdAfter)
    .map((f) => {
      const ageHours = Math.max(0, now - f.createdAt) / (60 * 60 * 1000)
      return {
        fact: f,
        score: f.notifyWorthiness + Math.pow(0.5, ageHours / POOL_RECENCY_HALF_LIFE_HOURS)
      }
    })
    .sort((a, b) =>
      a.score !== b.score ? b.score - a.score : a.fact.factID < b.fact.factID ? -1 : 1
    )

  const perBucket = new Map<string, number>()
  const out: PoolFact[] = []
  for (const { fact } of scored) {
    if (out.length >= maxItems) break
    const used = perBucket.get(fact.bucketID) ?? 0
    if (used >= maxPerBucket) continue
    perBucket.set(fact.bucketID, used + 1)
    out.push(fact)
  }
  return out
}

export function selectRecentContextFacts(facts: readonly PoolFact[], now: number): PoolFact[] {
  return selectPooledFacts(facts, now, {
    worthinessFloor: RECENT_CONTEXT_WORTHINESS_FLOOR,
    maxItems: RECENT_CONTEXT_MAX_ITEMS,
    maxPerBucket: RECENT_CONTEXT_MAX_PER_BUCKET,
    createdAfter: now - 15 * 60 * 1000
  })
}

export function relativeAge(ageMs: number): string {
  const seconds = Math.floor(ageMs / 1000)
  if (seconds < 60) return `${seconds}s ago`
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 48) return `${hours}h ago`
  return `${Math.floor(hours / 24)}d ago`
}

const POOL_INTRO = `Context only: use them to connect what the user is doing across apps. They are
not citable — never place them in bucket_entry_refs or fact_ids — and a point
they already cover must not be re-delivered from this bucket.`

function poolLines(facts: readonly PoolFact[], now: number): string {
  return facts
    .map((f) => {
      const app = [...f.appName].slice(0, 24).join('')
      const statement = [...f.statement].slice(0, 300).join('')
      return `- [${app}, ${relativeAge(now - f.createdAt)}] ${statement}`
    })
    .join('\n')
}

/** `== RELATED WORKSTREAM CONTEXT (<tag>) ==` — items printed without ids so
 *  the director cannot cite them. */
export function workstreamPromptSection(
  tag: string,
  facts: readonly PoolFact[],
  now: number
): string | null {
  if (facts.length === 0) return null
  return `== RELATED WORKSTREAM CONTEXT (${tag}) ==
Validated facts from other buckets in the same workstream, most relevant first.
${POOL_INTRO}
${poolLines(facts, now)}`
}

export function recentContextPromptSection(facts: readonly PoolFact[], now: number): string | null {
  if (facts.length === 0) return null
  return `== RECENT CONTEXT FROM OTHER WINDOWS (last 15 min) ==
Validated facts from other windows in the last 15 minutes, most relevant first.
${POOL_INTRO}
${poolLines(facts, now)}`
}
