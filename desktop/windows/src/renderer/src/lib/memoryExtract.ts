// LLM-based memory-log extraction — Windows port of macOS OnboardingMemoryLogImportService.
// Routes through backend POST /v1/memories/extract (managed memories → OpenRouter Luna SSOT)
// instead of Anthropic Haiku via /v2/chat/completions.
import { omiApi } from './apiClient'

export type MemorySource = 'chatgpt' | 'claude'

export type ExtractedMemories = { memories: string[]; profile: string }

// Loose normalization for the exact-match guard: lowercase, drop punctuation,
// collapse whitespace. Catches identical/near-identical strings; semantic dupes
// (NY vs New York) are handled by the backend extract prompt.
export function normalize(s: string): string {
  return s
    .toLowerCase()
    // Keep + and # so distinct facts like "C++" and "C#" do not normalize to the
    // same key and get dropped as duplicates of each other.
    .replace(/[^\p{L}\p{N}+#\s]/gu, '')
    .replace(/\s+/g, ' ')
    .trim()
}

// extractJSONObject now lives in the shared ./extractJson util (imported above);
// re-export it so the integration extractors that import it from ./memoryExtract
// keep resolving after the shared-util refactor.
export { extractJSONObject } from './extractJson'

// Send the pasted export through backend memories SSOT extract.
// Throws on transport/auth failure so callers can fall back to the local
// heuristic split.
export async function extractMemories(
  rawText: string,
  source: MemorySource = 'chatgpt',
  existing: string[] = []
): Promise<ExtractedMemories> {
  const trimmed = rawText.trim()
  if (!trimmed) return { memories: [], profile: '' }

  const res = await omiApi.post(
    '/v1/memories/extract',
    {
      text: trimmed.slice(0, 40_000),
      text_source: source,
      existing_memories: existing.slice(0, 200)
    },
    { timeout: 60_000 }
  )

  const data = res.data as { memories?: unknown; profile?: unknown }
  const raw = Array.isArray(data.memories)
    ? data.memories.filter((m): m is string => typeof m === 'string' && m.trim().length > 0)
    : []

  // Exact-match guard against existing memories and within-batch dupes, in case
  // the model slips one through. Semantic dedup is the prompt's job.
  const seen = new Set(existing.map(normalize))
  const memories: string[] = []
  for (const m of raw) {
    const key = normalize(m)
    if (!key || seen.has(key)) continue
    seen.add(key)
    memories.push(m)
  }

  const profile = typeof data.profile === 'string' ? data.profile : ''
  return { memories, profile }
}
