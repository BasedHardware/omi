// Shared orchestration for the "paste a ChatGPT/Claude memory-log" import, so the
// Settings → Advanced row and the Hub → Connections panel drive the SAME logic
// (no duplicated extraction/fallback/cap rules). The heavy lifting already lives
// in memoryExtract.ts (AI synthesis) and memoriesBulk.ts (batched write); this is
// the thin extract-with-heuristic-fallback + import glue that was previously
// inlined in AdvancedTab.
import { extractMemories, normalize, type MemorySource } from './memoryExtract'
import { postMemoriesBatched, type BatchImportTally } from './memoriesBulk'
import { toast } from './toast'

// Sanity cap for the no-AI line-split fallback: an enormous paste (a multi-thousand
// line export dump) would otherwise turn one extract into a single absurd import
// batch. The reviewed-list UI still shows exactly what will be sent, so cap the
// count, not the per-request size.
export const MAX_HEURISTIC_IMPORT_ITEMS = 500

// Discriminated on `via` so the heuristic-only fields (fallbackReason/truncated/
// totalBeforeCap) are reachable only after narrowing to the heuristic branch —
// mirrors StickyReadOutcome's shape.
export type PasteExtractResult =
  | { via: 'ai'; memories: string[]; profile: string }
  | {
      via: 'heuristic'
      memories: string[]
      profile: ''
      /** AI-path failure reason that triggered the fallback. */
      fallbackReason: string
      /** True when the heuristic list was capped at MAX_HEURISTIC_IMPORT_ITEMS. */
      truncated: boolean
      /** Full pre-cap count when truncated, so the caller can say "first N of M". */
      totalBeforeCap?: number
    }

/**
 * Extract durable memories from a pasted ChatGPT/Claude export. Tries the AI
 * synthesis path first; on any failure falls back to the local line-split parser
 * (window.omi.memoryImportParse), deduped against existing memories and capped.
 * Throws only if BOTH paths fail, so the caller surfaces a single hard error.
 */
export async function extractPasteMemories(
  dump: string,
  source: MemorySource,
  existing: string[]
): Promise<PasteExtractResult> {
  try {
    const { memories, profile } = await extractMemories(dump, source, existing)
    return { via: 'ai', memories, profile }
  } catch (aiError) {
    // AI extraction failed — fall back to a basic line split so the user isn't
    // blocked. Dedup against existing memories with the same normalize() the AI
    // path uses, then cap the count.
    const have = new Set(existing.map(normalize))
    const rawList = (await window.omi.memoryImportParse(dump)).filter(
      (m) => !have.has(normalize(m))
    )
    const truncated = rawList.length > MAX_HEURISTIC_IMPORT_ITEMS
    return {
      via: 'heuristic',
      memories: truncated ? rawList.slice(0, MAX_HEURISTIC_IMPORT_ITEMS) : rawList,
      profile: '',
      fallbackReason: (aiError as Error).message,
      truncated,
      totalBeforeCap: truncated ? rawList.length : undefined
    }
  }
}

/** The extract-phase toast (empty / heuristic-fallback), shared by both surfaces. */
export function toastForExtractResult(r: PasteExtractResult): void {
  if (r.memories.length === 0) {
    toast('No new memories found — they may already be saved', { tone: 'warn' })
    return
  }
  if (r.via === 'heuristic') {
    toast('AI extraction unavailable — used a basic line split', {
      tone: 'warn',
      body: r.truncated
        ? `${r.fallbackReason} · showing first ${r.memories.length} of ${r.totalBeforeCap} lines`
        : r.fallbackReason
    })
  }
}

/** Write the reviewed memories via the batched import endpoint. */
export async function importPasteMemories(memories: string[]): Promise<BatchImportTally> {
  return postMemoriesBatched(memories)
}
