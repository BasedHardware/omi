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

/** One frame waiting to be embedded. */
export type PendingEmbed = { frameId: number; text: string; hash: string; queuedAt: number }

/**
 * Bounded LRU of content-hash -> the frame whose row already holds that vector.
 * Storing the frame id (not the vector) is deliberate: 5000 x 12KB of vectors
 * would be ~60MB resident, whereas a cache hit can copy the vector straight from
 * the twin's already-persisted row for the cost of one indexed SELECT.
 */
export class RecentHashCache {
  private readonly map = new Map<string, number>()

  constructor(private readonly capacity: number = RECENT_HASH_CACHE_SIZE) {}

  /** The frame id previously embedded for this content, or undefined. Refreshes
   *  recency, so hot content is not evicted by a burst of one-off screens. */
  get(hash: string): number | undefined {
    const frameId = this.map.get(hash)
    if (frameId === undefined) return undefined
    this.map.delete(hash)
    this.map.set(hash, frameId)
    return frameId
  }

  set(hash: string, frameId: number): void {
    this.map.delete(hash)
    this.map.set(hash, frameId)
    // Map preserves insertion order, so the first key is the least recently used.
    while (this.map.size > this.capacity) {
      const oldest = this.map.keys().next()
      if (oldest.done) break
      this.map.delete(oldest.value)
    }
  }

  /** Drop a hash whose cached frame turned out to be unusable (row missing). */
  delete(hash: string): void {
    this.map.delete(hash)
  }

  get size(): number {
    return this.map.size
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

/** Content whose vector already exists on `sourceFrameId` — copy, don't re-embed.
 *  Carries `text` so the caller can fall back to a real embed if that row turns
 *  out to be gone (retention can prune the twin between cache write and flush). */
export type CopyGroup = EmbedGroup & { sourceFrameId: number }

export type EmbedBatchPlan = { toEmbed: EmbedGroup[]; toCopy: CopyGroup[] }

/**
 * Collapse a batch into the minimum set of API calls: group frames by content
 * hash (dedup within the batch), then split off the groups whose content was
 * embedded recently (dedup against the cache) so their vector can be copied from
 * the earlier frame's row.
 *
 * Pure: the cache is only read here. Hashes are recorded (in `noteEmbedded`)
 * once a vector is actually persisted, so a failed batch does not poison the
 * cache with a hash that has no row behind it.
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
    const sourceFrameId = cache.get(group.hash)
    // A cached source that is itself in this batch is not yet persisted — treat
    // it as fresh work rather than copying from a row that may not exist.
    if (sourceFrameId !== undefined && !group.frameIds.includes(sourceFrameId)) {
      toCopy.push({ ...group, sourceFrameId })
    } else {
      toEmbed.push(group)
    }
  }
  return { toEmbed, toCopy }
}
