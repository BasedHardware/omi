// Batching + dedup policy for the Rewind embedding indexer — pure, no I/O.
//
// Ports the macOS behaviour: work accumulates until 100 items OR 60s have passed
// since the oldest queued item, whichever comes first; and identical OCR text is
// never embedded twice. Dedup is the reason this is worth doing — consecutive
// screenshots of a mostly-static screen carry byte-identical text, and macOS
// reports the content-hash check cuts embedding API volume by roughly 20x.
//
// Dedup does NOT drop the duplicate frame: every frame still gets its own
// `rewind_embeddings` row (so it can be a vector hit), the row just reuses the
// vector already computed for its twin instead of paying for another API call.
import { contentHash } from './embedVector'

/** Flush as soon as this many items are pending. */
export const EMBED_BATCH_SIZE = 100

/** …or this long after the oldest pending item arrived, whichever is first. */
export const EMBED_FLUSH_INTERVAL_MS = 60_000

/** How many recently-embedded content hashes to remember across batches. */
export const RECENT_HASH_CACHE_SIZE = 5000

/**
 * Shortest OCR text worth embedding. A frame whose entire screen text is "OK" or
 * "1" carries no retrievable meaning, but still costs an API item and a 12KB
 * vector. NOTE: this floor is OURS — macOS has no such threshold. It only ever
 * suppresses content that could not have been usefully retrieved anyway, and the
 * frame stays keyword-searchable regardless.
 */
export const MIN_EMBED_TEXT_LEN = 10

/** True when a frame's OCR text carries enough content to be worth a vector. */
export function isEmbeddableText(text: string): boolean {
  return text.trim().length >= MIN_EMBED_TEXT_LEN
}

/** One frame waiting to be embedded. */
export type PendingEmbed = { frameId: number; text: string; hash: string; queuedAt: number }

/**
 * Bounded LRU set of content hashes whose vector is already stored. Holding the
 * hashes (not the vectors) is what keeps this cheap: 5000 x 12KB of vectors would
 * be ~60MB resident, whereas a hit just tells the caller to write a mapping row.
 */
export class RecentHashCache {
  private readonly hashes = new Map<string, true>()

  constructor(private readonly capacity: number = RECENT_HASH_CACHE_SIZE) {}

  /** True when this content was embedded recently. Refreshes recency, so hot
   *  content is not evicted by a burst of one-off screens. */
  has(hash: string): boolean {
    if (!this.hashes.has(hash)) return false
    this.hashes.delete(hash)
    this.hashes.set(hash, true)
    return true
  }

  add(hash: string): void {
    this.hashes.delete(hash)
    this.hashes.set(hash, true)
    // Map preserves insertion order, so the first key is the least recently used.
    while (this.hashes.size > this.capacity) {
      const oldest = this.hashes.keys().next()
      if (oldest.done) break
      this.hashes.delete(oldest.value)
    }
  }

  /** Drop a hash whose vector turned out to be gone (retention pruned it). */
  delete(hash: string): void {
    this.hashes.delete(hash)
  }

  clear(): void {
    this.hashes.clear()
  }

  get size(): number {
    return this.hashes.size
  }
}

/**
 * FIFO queue of frames awaiting embedding, with the 100-or-60s flush trigger.
 * Enqueueing the same frame twice (a re-OCR, a racing backfill) is a no-op.
 */
export class EmbedQueue {
  private pending: PendingEmbed[] = []
  private readonly queued = new Set<number>()

  /** Queue a frame. Blank text is rejected — there is nothing to embed. */
  add(frameId: number, text: string, now: number): boolean {
    if (!text.trim()) return false
    if (this.queued.has(frameId)) return false
    this.queued.add(frameId)
    this.pending.push({ frameId, text, hash: contentHash(text), queuedAt: now })
    return true
  }

  get size(): number {
    return this.pending.length
  }

  /** True when the batch is full, or the oldest item has waited out the interval. */
  shouldFlush(now: number): boolean {
    if (this.pending.length === 0) return false
    if (this.pending.length >= EMBED_BATCH_SIZE) return true
    return now - this.pending[0].queuedAt >= EMBED_FLUSH_INTERVAL_MS
  }

  /** Remove and return up to one batch, oldest first. */
  take(limit: number = EMBED_BATCH_SIZE): PendingEmbed[] {
    const batch = this.pending.slice(0, limit)
    this.pending = this.pending.slice(batch.length)
    for (const item of batch) this.queued.delete(item.frameId)
    return batch
  }
}

/** Unique content that must be sent to the embedding API, with every frame that shares it. */
export type EmbedGroup = { hash: string; text: string; frameIds: number[] }

/** Content whose vector is already stored — link to it, don't re-embed. Carries
 *  `text` so the caller can fall back to a real embed if that vector turns out to
 *  be gone (retention can prune it between the cache write and the flush). */
export type CopyGroup = EmbedGroup

export type EmbedBatchPlan = { toEmbed: EmbedGroup[]; toCopy: CopyGroup[] }

/**
 * Collapse a batch into the minimum set of API calls: group frames by content
 * hash (dedup within the batch), then split off the groups whose content was
 * embedded recently (dedup against the cache) so they can be linked to the vector
 * already stored for that content.
 *
 * Pure: the cache is only read here. A hash is recorded only once its vector is
 * actually persisted (the caller stores before caching), so a cached hash always
 * has a row behind it and a failed batch never poisons the cache.
 */
export function planEmbedBatch(items: PendingEmbed[], cache: RecentHashCache): EmbedBatchPlan {
  const byHash = new Map<string, EmbedGroup>()
  for (const item of items) {
    const group = byHash.get(item.hash)
    if (group) group.frameIds.push(item.frameId)
    else byHash.set(item.hash, { hash: item.hash, text: item.text, frameIds: [item.frameId] })
  }

  const toEmbed: EmbedGroup[] = []
  const toCopy: CopyGroup[] = []
  for (const group of byHash.values()) {
    if (cache.has(group.hash)) toCopy.push(group)
    else toEmbed.push(group)
  }
  return { toEmbed, toCopy }
}
