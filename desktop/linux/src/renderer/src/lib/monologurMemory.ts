// Monologur memory bridge.
//
// Monologur is the always-listening background agent. To make its interruptions
// feel personal it taps the same memory the Omi agent uses:
//   - READ: pull the user's saved memories (/v3/memories) and rank them against
//     the current conversation so the proactive prompt can reference real context.
//   - WRITE: when Monologur produces a genuinely useful, durable insight it stores
//     it back as a memory (tagged `monologur`) so it compounds over time — the same
//     store the main agent and brain map read from.
//
// All calls are best-effort and never block the proactive loop.

import { omiApi } from './apiClient'
import { rankMemories } from './memoryRank'
import type { Memory } from '../hooks/useMemories'

const MONOLOGUR_TAG = 'monologur'
const CACHE_TTL_MS = 5 * 60 * 1000

let memoryCache: { at: number; memories: Memory[] } | null = null

async function fetchMemories(force = false): Promise<Memory[]> {
  const now = Date.now()
  if (!force && memoryCache && now - memoryCache.at < CACHE_TTL_MS) {
    return memoryCache.memories
  }
  try {
    const r = await omiApi.get('/v3/memories', { params: { limit: 500, offset: 0 } })
    const list = (Array.isArray(r.data) ? r.data : (r.data?.memories ?? [])) as Memory[]
    memoryCache = { at: now, memories: list }
    return list
  } catch {
    return memoryCache?.memories ?? []
  }
}

/**
 * Build a short, ranked memory-context block for the proactive prompt. Returns an
 * empty string when there's nothing worth injecting (keeps the LLM call cheap).
 */
export async function getMonologurMemoryContext(conversationText: string): Promise<string> {
  const memories = await fetchMemories()
  if (memories.length === 0) return ''
  const ranked = rankMemories(memories, conversationText, 5)
  if (ranked.length === 0) return ''
  return [
    'Relevant memories about the user:',
    ...ranked.map((m) => `- ${m}`)
  ].join('\n')
}

/**
 * Persist a durable insight Monologur produced. Best-effort; failures are swallowed.
 * `dedupeKey` lets callers avoid writing the same line repeatedly.
 */
const written = new Set<string>()

export async function saveMonologurInsight(text: string): Promise<void> {
  const clean = text.trim()
  if (!clean) return
  // Rough dedupe so we don't spam the memory store with near-identical lines.
  const key = clean.toLowerCase().replace(/\s+/g, ' ').slice(0, 80)
  if (written.has(key)) return
  written.add(key)

  try {
    await omiApi.post('/v3/memories', {
      content: clean,
      tags: [MONOLOGUR_TAG]
    })
    // Invalidate the read cache so a later context pull sees the new memory.
    memoryCache = null
  } catch {
    // Don't let a memory write failure break the proactive loop.
  }
}
