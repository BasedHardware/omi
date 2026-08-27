/**
 * Director retrieval hop — port of macOS ContextDirectorRetrieval: at most one
 * bounded lookup per evaluation, three concurrent backend tool searches
 * (conversation summaries, verbatim conversation chunks, memories), each
 * failing independently to empty, with fail-closed item mapping and the
 * chunk-wins merge.
 */

import { singleLine } from './destinationKey'
import type { RetrievedItem } from './prompts'

export const RETRIEVAL_MIN_QUERY_LENGTH = 3
export const RETRIEVAL_MAX_QUERY_LENGTH = 200
export const RETRIEVAL_PER_SOURCE_LIMIT = 3
export const RETRIEVAL_CONVERSATION_COMBINED_LIMIT = 6
export const RETRIEVAL_MAX_PROMPT_ITEMS = 9
export const RETRIEVED_NAMESPACES = ['conversation:', 'memory:'] as const

/** Admission: flag on, no prior hop, flattened query length in [3, 200]. */
export function planRetrievalHop(
  lookupQuery: string | null,
  flagEnabled: boolean,
  priorHops: number
): string | null {
  if (!flagEnabled || priorHops !== 0 || lookupQuery === null) return null
  const flattened = singleLine(lookupQuery, RETRIEVAL_MAX_QUERY_LENGTH)
  return flattened.length >= RETRIEVAL_MIN_QUERY_LENGTH ? flattened : null
}

export interface RetrievalSource {
  kind: 'conversation' | 'memory'
  id: string
  title: string
  preview: string
  createdAt: string
}

export interface RetrievalSearches {
  conversations(query: string, limit: number): Promise<RetrievalSource[]>
  conversationChunks(query: string, limit: number): Promise<RetrievalSource[]>
  memories(query: string, limit: number): Promise<RetrievalSource[]>
}

export interface RetrievalOutcome {
  items: RetrievedItem[]
  allowedRefs: Set<string>
}

function mapItems(sources: RetrievalSource[], kind: 'conversation' | 'memory'): RetrievedItem[] {
  const out: RetrievedItem[] = []
  for (const source of sources) {
    if (out.length >= RETRIEVAL_PER_SOURCE_LIMIT) break
    if (source.kind !== kind) continue
    // Fail closed on malformed ids — no repair.
    if (source.id.length === 0 || source.id.length > 512) continue
    if (/\s/.test(source.id)) continue
    out.push({
      ref: `${kind}:${source.id}`,
      title: singleLine(source.title, 120),
      preview: singleLine(source.preview, 400),
      createdAt: singleLine(source.createdAt, 40)
    })
  }
  return out
}

/** Chunks and summaries share the conversation: namespace; chunks lead and
 *  win ref collisions; combined cap 6, then memories, prompt cap 9. */
export function mergeRetrievedItems(
  summaries: RetrievedItem[],
  chunks: RetrievedItem[],
  memories: RetrievedItem[]
): RetrievedItem[] {
  const seen = new Set<string>()
  const conversations: RetrievedItem[] = []
  for (const item of [...chunks, ...summaries]) {
    if (conversations.length >= RETRIEVAL_CONVERSATION_COMBINED_LIMIT) break
    if (seen.has(item.ref)) continue
    seen.add(item.ref)
    conversations.push(item)
  }
  return [...conversations, ...memories].slice(0, RETRIEVAL_MAX_PROMPT_ITEMS)
}

/** Run the three searches concurrently; each failure independently yields []. */
export async function retrieveForQuery(
  query: string,
  searches: RetrievalSearches
): Promise<RetrievalOutcome> {
  const safe = async (run: () => Promise<RetrievalSource[]>): Promise<RetrievalSource[]> => {
    try {
      return await run()
    } catch {
      return []
    }
  }
  const [summaries, chunks, memories] = await Promise.all([
    safe(() => searches.conversations(query, RETRIEVAL_PER_SOURCE_LIMIT)),
    safe(() => searches.conversationChunks(query, RETRIEVAL_PER_SOURCE_LIMIT)),
    safe(() => searches.memories(query, RETRIEVAL_PER_SOURCE_LIMIT))
  ])
  const items = mergeRetrievedItems(
    mapItems(summaries, 'conversation'),
    mapItems(chunks, 'conversation'),
    mapItems(memories, 'memory')
  )
  return { items, allowedRefs: new Set(items.map((i) => i.ref)) }
}

/** Split cited refs into bucket-entry vs retrieved namespaces. */
export function partitionCitedRefs(refs: readonly string[]): {
  bucketRefs: string[]
  retrievedRefs: string[]
} {
  const bucketRefs: string[] = []
  const retrievedRefs: string[] = []
  for (const ref of refs) {
    if (RETRIEVED_NAMESPACES.some((ns) => ref.startsWith(ns))) retrievedRefs.push(ref)
    else bucketRefs.push(ref)
  }
  return { bucketRefs, retrievedRefs }
}

/** Order-preserving dedup filter against the per-call allowlist; an absent or
 *  failed hop leaves the allowlist empty so retrieved citations fail closed. */
export function validatedRetrievedRefs(
  refs: readonly string[],
  allowed: ReadonlySet<string>
): string[] {
  const out: string[] = []
  const seen = new Set<string>()
  for (const ref of refs) {
    if (!allowed.has(ref) || seen.has(ref)) continue
    seen.add(ref)
    out.push(ref)
  }
  return out
}
