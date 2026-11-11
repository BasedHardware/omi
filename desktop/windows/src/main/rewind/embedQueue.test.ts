import { describe, expect, it } from 'vitest'
import {
  EMBED_BATCH_SIZE,
  EMBED_FLUSH_INTERVAL_MS,
  EmbedQueue,
  RecentHashCache,
  isEmbeddableText,
  planEmbedBatch,
  type PendingEmbed
} from './embedQueue'
import { contentHash } from './embedVector'

const item = (frameId: number, text: string, queuedAt = 0): PendingEmbed => ({
  frameId,
  text,
  hash: contentHash(text),
  queuedAt
})

describe('EmbedQueue flush trigger', () => {
  it('does not flush an empty queue', () => {
    expect(new EmbedQueue().shouldFlush(Date.now())).toBe(false)
  })

  it('flushes as soon as the batch is full (100 items)', () => {
    const q = new EmbedQueue()
    for (let i = 0; i < EMBED_BATCH_SIZE - 1; i++) q.add(i, `text ${i}`, 1000)
    expect(q.shouldFlush(1000)).toBe(false) // 99 queued, no time elapsed
    q.add(999, 'text 999', 1000)
    expect(q.size).toBe(EMBED_BATCH_SIZE)
    expect(q.shouldFlush(1000)).toBe(true)
  })

  it('flushes a partial batch once the oldest item has waited out the interval', () => {
    const q = new EmbedQueue()
    q.add(1, 'only item', 1000)
    expect(q.shouldFlush(1000 + EMBED_FLUSH_INTERVAL_MS - 1)).toBe(false)
    expect(q.shouldFlush(1000 + EMBED_FLUSH_INTERVAL_MS)).toBe(true)
  })

  // The deadline belongs to the OLDEST item — a steady trickle of new frames
  // must not keep pushing the flush out forever.
  it('measures the interval from the oldest item, not the newest', () => {
    const q = new EmbedQueue()
    q.add(1, 'old', 1000)
    q.add(2, 'new', 1000 + EMBED_FLUSH_INTERVAL_MS)
    expect(q.shouldFlush(1000 + EMBED_FLUSH_INTERVAL_MS)).toBe(true)
  })

  it('takes at most one batch, oldest first, and drains the rest later', () => {
    const q = new EmbedQueue()
    for (let i = 0; i < EMBED_BATCH_SIZE + 5; i++) q.add(i, `text ${i}`, 0)
    const batch = q.take()
    expect(batch).toHaveLength(EMBED_BATCH_SIZE)
    expect(batch[0].frameId).toBe(0)
    expect(q.size).toBe(5)
  })

  it('rejects blank text and duplicate frame ids', () => {
    const q = new EmbedQueue()
    expect(q.add(1, 'real text', 0)).toBe(true)
    expect(q.add(1, 'real text', 0)).toBe(false) // same frame, already queued
    expect(q.add(2, '   ', 0)).toBe(false) // nothing to embed
    expect(q.size).toBe(1)
  })

  it('lets a frame be re-queued after its batch was taken', () => {
    const q = new EmbedQueue()
    q.add(1, 'text', 0)
    q.take()
    expect(q.add(1, 'text', 0)).toBe(true)
  })
})

describe('RecentHashCache', () => {
  it('evicts the least recently used entry past capacity', () => {
    const cache = new RecentHashCache(2)
    cache.add('a')
    cache.add('b')
    cache.add('c')
    expect(cache.size).toBe(2)
    expect(cache.has('a')).toBe(false) // evicted
    expect(cache.has('b')).toBe(true)
    expect(cache.has('c')).toBe(true)
  })

  it('a read refreshes recency, so hot content survives a burst', () => {
    const cache = new RecentHashCache(2)
    cache.add('a')
    cache.add('b')
    cache.has('a') // 'a' is now the most recently used, so 'b' is next out
    cache.add('c')
    expect(cache.has('a')).toBe(true)
    expect(cache.has('b')).toBe(false)
  })

  it('forgets a hash whose vector was pruned', () => {
    const cache = new RecentHashCache()
    cache.add('a')
    cache.delete('a')
    expect(cache.has('a')).toBe(false)
  })
})

describe('isEmbeddableText', () => {
  // Our addition, not Mac's: a screen whose entire text is "OK" costs an API item
  // and a 12KB vector while carrying nothing anyone could retrieve.
  it('rejects trivially short text and accepts real content', () => {
    expect(isEmbeddableText('OK')).toBe(false)
    expect(isEmbeddableText('   ')).toBe(false)
    expect(isEmbeddableText('quarterly revenue projections')).toBe(true)
  })
})

describe('planEmbedBatch', () => {
  // The ~20x API saving: consecutive screenshots of a static screen carry
  // byte-identical OCR text and must cost exactly one embedding call.
  it('dedups identical content within a batch to one API call, keeping every frame', () => {
    const { toEmbed, toCopy } = planEmbedBatch(
      [item(1, 'same screen'), item(2, 'same screen'), item(3, 'different')],
      new RecentHashCache()
    )
    expect(toCopy).toEqual([])
    expect(toEmbed).toHaveLength(2)
    const shared = toEmbed.find((g) => g.text === 'same screen')
    // One call, but BOTH frames stay findable — dedup saves the call, not the frame.
    expect(shared?.frameIds).toEqual([1, 2])
  })

  it('links rather than re-embeds content seen in an earlier batch', () => {
    const cache = new RecentHashCache()
    cache.add(contentHash('seen before'))
    const { toEmbed, toCopy } = planEmbedBatch(
      [item(7, 'seen before'), item(8, 'brand new')],
      cache
    )
    expect(toEmbed.map((g) => g.text)).toEqual(['brand new'])
    expect(toCopy).toHaveLength(1)
    expect(toCopy[0].frameIds).toEqual([7])
    expect(toCopy[0].text).toBe('seen before') // carried, so a pruned vector can re-embed
  })

  // Regression: an earlier version skipped the link when the cached hash had been
  // first seen on a frame in this same batch, turning a free link into a PAID
  // second API call for the same content. A cached hash always has a stored
  // vector (the caller stores before caching), so there is nothing to guard.
  it('links every frame carrying already-embedded content, never re-paying', () => {
    const cache = new RecentHashCache()
    cache.add(contentHash('text'))
    const { toEmbed, toCopy } = planEmbedBatch([item(5, 'text'), item(6, 'text')], cache)
    expect(toEmbed).toEqual([])
    expect(toCopy).toHaveLength(1)
    expect(toCopy[0].frameIds).toEqual([5, 6])
  })
})
