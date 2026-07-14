// Pipeline tests for the Rewind embedding indexer.
//
// The service is the only impure piece (DB + network), so both are mocked: the
// real `ipc/db` pulls in better-sqlite3 (Electron ABI — won't load under
// plain-node vitest) and the real client imports `electron`. What is exercised
// for real is the wiring the mocks sit between: the backfill sweep, the
// batch/dedup plan, the persistence calls, and the degrade-to-nothing paths.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { RewindFrame } from '../../shared/types'

const db = vi.hoisted(() => ({
  rewindFramesNeedingEmbedding: vi.fn(),
  upsertRewindEmbedding: vi.fn(),
  linkRewindEmbedding: vi.fn()
}))
const client = vi.hoisted(() => ({ embedBatch: vi.fn(), embedOne: vi.fn() }))

vi.mock('../ipc/db', () => db)
vi.mock('./embeddingClient', () => client)

import {
  __resetRewindEmbeddingForTests,
  configureRewindEmbedSession,
  embedRewindQuery,
  enqueueRewindEmbedding,
  rewindEmbeddingsAvailable
} from './embeddingService'
import { EMBED_MODEL } from './embedVector'

const SESSION = { desktopApiBase: 'https://desktop.example', token: 'tok' }

const frame = (id: number, ocrText: string): RewindFrame => ({
  id,
  ts: id * 1000,
  app: 'Code',
  windowTitle: 'w',
  processName: 'code.exe',
  ocrText,
  imagePath: `C:\\f\\${id}.jpg`,
  width: 1,
  height: 1,
  indexed: 1
})

const vec = (seed: number): Float32Array => Float32Array.from([seed, 0, 0])

/** Let the backfill's awaits + its 200ms inter-batch pauses run to completion. */
async function settle(): Promise<void> {
  await vi.advanceTimersByTimeAsync(60_000)
}

/** Queue `frames` for the backfill to find, then nothing (i.e. caught up). */
function supply(...batches: RewindFrame[][]): void {
  for (const b of batches) db.rewindFramesNeedingEmbedding.mockReturnValueOnce(b)
  db.rewindFramesNeedingEmbedding.mockReturnValue([])
}

beforeEach(() => {
  vi.useFakeTimers()
  __resetRewindEmbeddingForTests()
  vi.clearAllMocks()
  db.linkRewindEmbedding.mockReturnValue(true) // the vector is there unless a test says otherwise
  client.embedBatch.mockImplementation(async (_s: unknown, texts: string[]) =>
    texts.map((_, i) => vec(i + 1))
  )
})

afterEach(() => {
  __resetRewindEmbeddingForTests()
  vi.useRealTimers()
})

describe('session gating', () => {
  it('is inert until a session is relayed in, and again after sign-out', async () => {
    expect(rewindEmbeddingsAvailable()).toBe(false)
    supply([frame(1, 'some frame text')])

    // No session: nothing is embedded, even with work available.
    enqueueRewindEmbedding(1, 'text')
    await settle()
    expect(client.embedBatch).not.toHaveBeenCalled()

    configureRewindEmbedSession(SESSION)
    expect(rewindEmbeddingsAvailable()).toBe(true)

    configureRewindEmbedSession(null)
    expect(rewindEmbeddingsAvailable()).toBe(false)
  })

  it('ignores a session with no token (treated as signed out)', () => {
    configureRewindEmbedSession({ desktopApiBase: 'https://x', token: '' })
    expect(rewindEmbeddingsAvailable()).toBe(false)
  })
})

describe('backfill', () => {
  // The startup race: main is ready long before the renderer has a token, so the
  // sweep has to be kicked by the session's arrival, not by app-ready.
  it('starts when the session arrives and embeds frames that lack a vector', async () => {
    supply([frame(1, 'alpha content'), frame(2, 'beta content')])
    configureRewindEmbedSession(SESSION)
    await settle()

    expect(client.embedBatch).toHaveBeenCalledTimes(1)
    const [, texts, taskType] = client.embedBatch.mock.calls[0]
    expect(texts).toEqual(['alpha content', 'beta content'])
    expect(taskType).toBe('RETRIEVAL_DOCUMENT') // stored passages, not a query
    expect(db.upsertRewindEmbedding).toHaveBeenCalledWith(
      1,
      expect.any(String),
      vec(1),
      EMBED_MODEL
    )
    expect(db.upsertRewindEmbedding).toHaveBeenCalledWith(
      2,
      expect.any(String),
      vec(2),
      EMBED_MODEL
    )
  })

  // The storage half of the dedup: one 12KB vector for the content, one cheap
  // mapping row per frame — so both twins stay findable without paying twice.
  it('sends identical OCR text to the API once and stores ONE vector under a shared hash', async () => {
    supply([frame(1, 'same screen'), frame(2, 'same screen'), frame(3, 'other screen')])
    configureRewindEmbedSession(SESSION)
    await settle()

    expect(client.embedBatch.mock.calls[0][1]).toEqual(['same screen', 'other screen'])
    const calls = db.upsertRewindEmbedding.mock.calls
    expect(calls).toHaveLength(3) // every frame is mapped...
    const hashes = new Set(calls.map((c) => c[1] as string))
    expect(hashes.size).toBe(2) // ...but only two distinct contents exist
    // The twins share a hash AND the same vector.
    const [h1, h2] = [calls[0][1], calls[1][1]]
    expect(h1).toBe(h2)
    expect(calls[0][2]).toEqual(vec(1))
    expect(calls[1][2]).toEqual(vec(1))
  })

  it('links to the stored vector when the same content recurs, with no API call', async () => {
    supply([frame(1, 'repeat me please')], [frame(2, 'repeat me please')])
    configureRewindEmbedSession(SESSION)
    await settle()

    // Second sighting cost no API call and no second vector — just a mapping row.
    expect(client.embedBatch).toHaveBeenCalledTimes(1)
    expect(db.linkRewindEmbedding).toHaveBeenCalledWith(2, expect.any(String))
    expect(db.upsertRewindEmbedding).toHaveBeenCalledTimes(1) // frame 1 only
  })

  it('re-embeds when the content-cache hit points at a vector retention has pruned', async () => {
    supply([frame(1, 'repeat me please')], [frame(2, 'repeat me please')])
    db.linkRewindEmbedding.mockReturnValue(false) // vector gone
    configureRewindEmbedSession(SESSION)
    await settle()

    // Falls back to a real embed rather than leaving frame 2 unsearchable.
    expect(client.embedBatch).toHaveBeenCalledTimes(2)
    expect(db.upsertRewindEmbedding).toHaveBeenCalledWith(
      2,
      expect.any(String),
      vec(1),
      EMBED_MODEL
    )
  })

  it('stops at the 5000-per-launch cap even when work never runs out', async () => {
    let next = 1
    db.rewindFramesNeedingEmbedding.mockImplementation((limit: number) =>
      Array.from({ length: limit }, () => frame(next, `unique text ${next++}`))
    )
    configureRewindEmbedSession(SESSION)
    await settle()

    // 5000 frames / 100-item batches — and then it stops instead of spinning.
    expect(client.embedBatch).toHaveBeenCalledTimes(50)
    expect(db.upsertRewindEmbedding).toHaveBeenCalledTimes(5000)
  })

  // C3 regression: previously ONE transient failure ended the whole launch's
  // backfill. The failed frames kept coming back from the query, the in-memory
  // filter emptied the page, and an empty page was read as "caught up" — silently
  // abandoning the remaining ~4,900 frames of budget until the next restart.
  it('keeps going after a transient failure instead of mistaking it for "caught up"', async () => {
    let next = 1
    db.rewindFramesNeedingEmbedding.mockImplementation((limit: number, exclude: number[] = []) => {
      const excluded = new Set(exclude)
      const out: RewindFrame[] = []
      while (out.length < limit && next <= 250) {
        if (!excluded.has(next)) out.push(frame(next, `unique text ${next}`))
        next++
      }
      return out
    })
    client.embedBatch.mockRejectedValueOnce(new Error('transient blip')) // batch 1 dies
    configureRewindEmbedSession(SESSION)
    await settle()

    // It must have moved PAST the failed batch and embedded the rest.
    expect(client.embedBatch.mock.calls.length).toBeGreaterThan(1)
    expect(db.upsertRewindEmbedding.mock.calls.length).toBeGreaterThan(100)
  })

  // M2 regression: the cap counted frames QUERIED, not frames the queue accepted,
  // so any drop (already queued, queue full) silently ate budget and the backfill
  // under-delivered without saying so.
  it('spends its budget on frames the queue accepted, not on rows the query returned', async () => {
    let next = 100_000
    // Every page ends with a row the queue will REJECT (a frame already in the
    // page). The old code counted it anyway and lost that much budget per page.
    db.rewindFramesNeedingEmbedding.mockImplementation((limit: number) => {
      const rows = Array.from({ length: limit }, () => frame(++next, `budget text ${next}`))
      if (rows.length > 1) rows[rows.length - 1] = rows[0] // the duplicate `add()` refuses
      return rows
    })
    configureRewindEmbedSession(SESSION)
    await settle()

    // Every frame the queue ACCEPTED was stored — one way or the other (a fresh
    // vector, or a link to content already embedded). The rejected duplicates
    // cost no budget, so the full 5000 is delivered rather than quietly eroded.
    const stored =
      db.upsertRewindEmbedding.mock.calls.length + db.linkRewindEmbedding.mock.calls.length
    expect(stored).toBe(5000)
  })

  it('gives up on frames whose batch failed, rather than retrying them forever', async () => {
    client.embedBatch.mockRejectedValue(new Error('proxy down'))
    db.rewindFramesNeedingEmbedding.mockImplementation(() => [
      frame(1, 'first frame text'),
      frame(2, 'second frame text')
    ])
    configureRewindEmbedSession(SESSION)
    await settle()

    // The same two frames keep coming back from the DB (no vector was written),
    // but the launch-local failure set stops the sweep from looping on them.
    expect(client.embedBatch).toHaveBeenCalledTimes(1)
    expect(db.upsertRewindEmbedding).not.toHaveBeenCalled()
  })
})

describe('embedRewindQuery', () => {
  it('embeds a query with the asymmetric RETRIEVAL_QUERY task type', async () => {
    client.embedOne.mockResolvedValue(new Float32Array(3072))
    configureRewindEmbedSession(SESSION)

    const result = await embedRewindQuery('what did I read about vectors')
    expect(result).toBeInstanceOf(Float32Array)
    expect(client.embedOne.mock.calls[0][2]).toBe('RETRIEVAL_QUERY')
  })

  // Every degraded path returns null so the caller silently falls back to
  // keyword-only results — semantic search must never break search.
  it('returns null (never throws) when signed out, blank, or the API fails', async () => {
    expect(await embedRewindQuery('query')).toBeNull() // no session

    configureRewindEmbedSession(SESSION)
    expect(await embedRewindQuery('   ')).toBeNull() // nothing to embed
    expect(client.embedOne).not.toHaveBeenCalled()

    client.embedOne.mockRejectedValue(new Error('proxy down'))
    expect(await embedRewindQuery('query')).toBeNull() // API failure

    client.embedOne.mockResolvedValue(new Float32Array(8)) // wrong dimension
    expect(await embedRewindQuery('query')).toBeNull()
  })
})
