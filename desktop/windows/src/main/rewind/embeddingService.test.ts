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
  getRewindEmbedding: vi.fn()
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
  db.getRewindEmbedding.mockReturnValue(null)
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
    supply([frame(1, 'text')])

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
    supply([frame(1, 'alpha'), frame(2, 'beta')])
    configureRewindEmbedSession(SESSION)
    await settle()

    expect(client.embedBatch).toHaveBeenCalledTimes(1)
    const [, texts, taskType] = client.embedBatch.mock.calls[0]
    expect(texts).toEqual(['alpha', 'beta'])
    expect(taskType).toBe('RETRIEVAL_DOCUMENT') // stored passages, not a query
    expect(db.upsertRewindEmbedding).toHaveBeenCalledWith(1, vec(1), EMBED_MODEL)
    expect(db.upsertRewindEmbedding).toHaveBeenCalledWith(2, vec(2), EMBED_MODEL)
  })

  it('sends identical OCR text to the API once, but stores a row per frame', async () => {
    supply([frame(1, 'same screen'), frame(2, 'same screen'), frame(3, 'other')])
    configureRewindEmbedSession(SESSION)
    await settle()

    expect(client.embedBatch.mock.calls[0][1]).toEqual(['same screen', 'other'])
    expect(db.upsertRewindEmbedding).toHaveBeenCalledTimes(3)
    // Both twins get the SAME vector — one call, two rows.
    expect(db.upsertRewindEmbedding).toHaveBeenCalledWith(1, vec(1), EMBED_MODEL)
    expect(db.upsertRewindEmbedding).toHaveBeenCalledWith(2, vec(1), EMBED_MODEL)
  })

  it('copies a vector from an earlier frame when the same content recurs', async () => {
    supply([frame(1, 'repeat')], [frame(2, 'repeat')])
    db.getRewindEmbedding.mockReturnValue(vec(1)) // frame 1's persisted row
    configureRewindEmbedSession(SESSION)
    await settle()

    // Second sighting cost no API call, but still got its own row.
    expect(client.embedBatch).toHaveBeenCalledTimes(1)
    expect(db.getRewindEmbedding).toHaveBeenCalledWith(1)
    expect(db.upsertRewindEmbedding).toHaveBeenCalledWith(2, vec(1), EMBED_MODEL)
  })

  it('stops at the 5000-per-launch cap even when work never runs out', async () => {
    let next = 1
    db.rewindFramesNeedingEmbedding.mockImplementation((limit: number) =>
      Array.from({ length: limit }, () => frame(next, `text ${next++}`))
    )
    configureRewindEmbedSession(SESSION)
    await settle()

    // 5000 frames / 100-item batches — and then it stops instead of spinning.
    expect(client.embedBatch).toHaveBeenCalledTimes(50)
    expect(db.upsertRewindEmbedding).toHaveBeenCalledTimes(5000)
  })

  it('gives up on frames whose batch failed, rather than retrying them forever', async () => {
    client.embedBatch.mockRejectedValue(new Error('proxy down'))
    db.rewindFramesNeedingEmbedding.mockImplementation(() => [frame(1, 'a'), frame(2, 'b')])
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
