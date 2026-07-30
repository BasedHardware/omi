/**
 * Live-prod E2E for conversation sync — simulates a SCREEN session end-to-end at
 * the lib level, against the REAL api.omi.me:
 *
 *   1. Two transcribe-stream sockets (the mic + system lanes, mode 'transcribe'
 *      endpoint via the production URL builder) fed real synthesized speech,
 *      the system lane starting ~2.5s later (wall-clock separation).
 *   2. Segments collected through the REAL createSegmentStore (wall-clock
 *      stamping) and merged with the REAL mergeLanes.
 *   3. POST /v1/conversations/from-segments (the REAL buildFromSegmentsRequest),
 *      labeled as an Omi test fixture (the first segment becomes the title —
 *      known prod quirk — so the test data is self-identifying).
 *   4. Poll until status 'completed' (from-segments has an async processing
 *      tail; DELETE during 'processing' can race and resurrect), assert the
 *      conversation is well-formed and that findCloudMatch (the outbox's
 *      unconfirmed-dedupe rule) locates it in the real list.
 *   5. DELETE it and verify by re-listing.
 *
 * TEST-DATA HYGIENE (hard rule): everything created is labeled 'Omi test
 * fixture', deleted after completion, and the deletion is verified by re-list;
 * afterAll double-checks cleanup even when an assertion failed.
 *
 * GATED exactly like the PTT live suite — skips entirely without the explicit
 * opt-in, so it never runs in `pnpm test`:
 *
 *   pnpm test:e2e:conv-sync     # sets OMI_E2E=1, generates fixtures if missing
 *
 * Budget: one from-segments POST (30/hour limit), ~15s of the streaming budget.
 */
import { execFileSync } from 'node:child_process'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import axios from 'axios'
import WebSocket from 'ws'
import { describe, it, expect, beforeAll, afterAll } from 'vitest'
import { buildListenEndpoint } from '../../../../main/ipc/omiListen'
import { createSegmentStore, type SegmentStore } from './segmentRetention'
import { mergeLanes } from './mergeLanes'
import { FROM_SEGMENTS_PATH, buildFromSegmentsRequest, findCloudMatch } from './outbox'
import type { BackendSegment, SyncSegment } from '../../../../shared/types'
// eslint-disable-next-line @typescript-eslint/ban-ts-comment
// @ts-ignore -- plain .mjs helper without type declarations
import { readDotEnv, decodeJwt, exchangeRefreshToken } from '../../../../../scripts/lib/omi-auth.mjs'

const HERE = path.dirname(fileURLToPath(import.meta.url))
const WINDOWS_ROOT = path.resolve(HERE, '../../../../..')

// ---------------------------------------------------------------------------
// Env / gating (same contract as pttTranscribe.e2e.test.ts)
// ---------------------------------------------------------------------------
const dotEnv: Record<string, string> = readDotEnv(path.join(WINDOWS_ROOT, '.env'))
const DIRECT_TOKEN = process.env.OMI_E2E_TOKEN ?? ''
const OPTED_IN = process.env.OMI_E2E === '1' || Boolean(DIRECT_TOKEN)
const REFRESH_TOKEN =
  process.env.OMI_E2E_REFRESH_TOKEN ??
  dotEnv.OMI_E2E_REFRESH_TOKEN ??
  process.env.OMI_REFRESH_TOKEN ??
  dotEnv.OMI_REFRESH_TOKEN ??
  ''
const FIREBASE_API_KEY = process.env.VITE_FIREBASE_API_KEY ?? dotEnv.VITE_FIREBASE_API_KEY ?? ''
const OMI_BASE = process.env.VITE_OMI_API_BASE ?? dotEnv.VITE_OMI_API_BASE ?? 'https://api.omi.me'
const FIXTURE_DIR = path.join(WINDOWS_ROOT, 'test', 'fixtures', 'audio')

const FIXTURE_LABEL = 'Omi test fixture — automated conversation-sync harness, safe to delete.'

let idToken = ''
let createdId: string | null = null
let deletedVerified = false

function api(): { headers: Record<string, string> } {
  return { headers: { Authorization: `Bearer ${idToken}` } }
}

// ---------------------------------------------------------------------------
// One transcribe-stream lane: connect, feed paced PCM, finalize, and pipe every
// raw segment batch into the lane's SegmentStore stamped at ARRIVAL — exactly
// what useRecorder's onSegments wiring does in the app.
// ---------------------------------------------------------------------------
function streamLane(
  name: string,
  pcm: Buffer,
  store: SegmentStore,
  opts: { startDelayMs?: number } = {}
): Promise<{ batches: number }> {
  const { startDelayMs = 0 } = opts
  return new Promise((resolve, reject) => {
    setTimeout(() => {
      const url = buildListenEndpoint('transcribe', 'en')
      const ws = new WebSocket(url.replace('wss://api.omi.me', OMI_BASE.replace(/^http/, 'ws')), {
        headers: { Authorization: `Bearer ${idToken}` }
      })
      let batches = 0
      const deadline = setTimeout(() => finish(), 30_000)
      const finish = (): void => {
        clearTimeout(deadline)
        try {
          ws.terminate()
        } catch {
          /* closed */
        }
        resolve({ batches })
      }
      ws.on('open', () => {
        void (async () => {
          for (let off = 0; off < pcm.length; off += 8192) {
            ws.send(pcm.subarray(off, off + 8192))
            await new Promise((r) => setTimeout(r, 100))
          }
          ws.send('finalize')
          setTimeout(finish, 6_000) // bounded trailing-segment window
        })()
      })
      ws.on('message', (data, isBinary) => {
        if (isBinary) return
        const text = data.toString().trim()
        if (!text || text === 'ping') return
        try {
          const json = JSON.parse(text)
          if (Array.isArray(json)) {
            batches++
            store.add(json as BackendSegment[], Date.now())
            console.log(
              `[conv-sync-e2e] ${name} batch ${batches}: ${(json as BackendSegment[]).map((s) => JSON.stringify(s.text)).join(', ')}`
            )
          }
        } catch {
          /* non-JSON frame */
        }
      })
      ws.on('unexpected-response', (_req, res) => reject(new Error(`${name}: HTTP ${res.statusCode}`)))
      ws.on('error', (err) => reject(new Error(`${name}: ${err.message}`)))
    }, startDelayMs)
  })
}

async function getConversation(id: string): Promise<{ status: number; body: Record<string, unknown> }> {
  const r = await axios.get(`${OMI_BASE}/v1/conversations/${id}`, { ...api(), validateStatus: () => true })
  return { status: r.status, body: r.data ?? {} }
}

async function listConversations(limit = 30): Promise<Array<Record<string, unknown>>> {
  const r = await axios.get(`${OMI_BASE}/v1/conversations`, { ...api(), params: { limit, offset: 0 } })
  return Array.isArray(r.data) ? r.data : []
}

async function pollUntilCompleted(id: string, timeoutMs: number): Promise<Record<string, unknown>> {
  const t0 = Date.now()
  for (;;) {
    const { status, body } = await getConversation(id)
    const st = (body.status as string) ?? ''
    if (status === 200 && st === 'completed') return body
    if (status === 200 && st === 'failed') throw new Error(`conversation ${id} processing FAILED`)
    if (Date.now() - t0 > timeoutMs) throw new Error(`timed out waiting for completed (last: ${status}/${st})`)
    await new Promise((r) => setTimeout(r, 3_000))
  }
}

// ---------------------------------------------------------------------------
describe.skipIf(!OPTED_IN || (!DIRECT_TOKEN && !REFRESH_TOKEN))('conversation sync e2e (live api.omi.me)', () => {
  beforeAll(async () => {
    if (!fs.existsSync(path.join(FIXTURE_DIR, 'manifest.json'))) {
      execFileSync('node', [path.join(WINDOWS_ROOT, 'scripts', 'gen-audio-fixtures.mjs')], {
        stdio: 'inherit',
        timeout: 180_000
      })
    }
    idToken = DIRECT_TOKEN || ((await exchangeRefreshToken(REFRESH_TOKEN, FIREBASE_API_KEY)) as string)
    const payload = decodeJwt(idToken) as { user_id?: string; sub?: string }
    console.log(`[conv-sync-e2e] uid=${payload.user_id ?? payload.sub} base=${OMI_BASE}`)
  }, 240_000)

  afterAll(async () => {
    // Hygiene backstop: if the test failed before its own delete, clean up here.
    if (!createdId || deletedVerified) return
    try {
      await pollUntilCompleted(createdId, 90_000).catch(() => undefined) // best effort past 'processing'
      await axios.delete(`${OMI_BASE}/v1/conversations/${createdId}`, { ...api(), validateStatus: () => true })
      const list = await listConversations()
      console.log(
        `[conv-sync-e2e] afterAll cleanup: ${createdId} ${list.some((c) => c.id === createdId) ? 'STILL PRESENT — delete manually' : 'deleted'}`
      )
    } catch (e) {
      console.warn(`[conv-sync-e2e] afterAll cleanup failed for ${createdId}:`, (e as Error).message)
    }
  }, 180_000)

  it('screen session → two lanes → merge → from-segments → completed → delete (verified)', async () => {
    // ---- 1. The session: two lanes, system starting ~2.5s later ------------
    const sessionStart = Date.now()
    const micStore = createSegmentStore(sessionStart)
    const systemStore = createSegmentStore(sessionStart)
    const pcm = fs.readFileSync(path.join(FIXTURE_DIR, 'speech-hello.pcm'))
    const SYSTEM_DELAY_MS = 2_500
    await Promise.all([
      streamLane('mic', pcm, micStore),
      streamLane('system', pcm, systemStore, { startDelayMs: SYSTEM_DELAY_MS })
    ])
    const endedAt = Date.now()

    const micSegs = micStore.list()
    const sysSegs = systemStore.list()
    console.log(`[conv-sync-e2e] mic segments=${micSegs.length} system segments=${sysSegs.length}`)
    expect(micSegs.length, 'mic lane transcribed').toBeGreaterThan(0)
    expect(sysSegs.length, 'system lane transcribed').toBeGreaterThan(0)
    expect(micSegs.map((s) => s.text).join(' ')).toMatch(/hello/i)
    // Wall-clock property: the system lane started 2.5s later, so its first
    // stamped offset must reflect that (stream time alone would say ~0).
    expect(sysSegs[0].start).toBeGreaterThan(1)

    // ---- 2. Merge + label ---------------------------------------------------
    const merged = mergeLanes(micSegs, sysSegs)
    expect(merged.length).toBe(micSegs.length + sysSegs.length)
    const label: SyncSegment = {
      text: FIXTURE_LABEL,
      speaker: 'SPEAKER_0',
      speaker_id: 0,
      is_user: true,
      person_id: null,
      start: 0,
      end: 0.5
    }
    const segments = [label, ...merged]

    // ---- 3. POST from-segments (the real request builder) ------------------
    const conv = {
      id: `local-e2e-${Date.now()}`,
      startedAt: sessionStart,
      endedAt,
      segments,
      syncState: 'pending' as const
    }
    const req = buildFromSegmentsRequest(conv, 'en')
    const post = await axios.post(`${OMI_BASE}${FROM_SEGMENTS_PATH}`, req, {
      ...api(),
      validateStatus: () => true
    })
    console.log(`[conv-sync-e2e] POST from-segments → ${post.status} id=${post.data?.id}`)
    expect(post.status).toBe(200)
    expect(post.data?.id).toBeTruthy()
    createdId = post.data.id as string

    // ---- 4. Poll to completed; assert well-formed ---------------------------
    const done = await pollUntilCompleted(createdId, 120_000)
    const structured = (done.structured ?? {}) as Record<string, unknown>
    console.log(
      `[conv-sync-e2e] completed: title=${JSON.stringify(structured.title)} category=${structured.category} segments=${(done.transcript_segments as unknown[])?.length}`
    )
    expect(String(structured.title ?? '')).toMatch(/omi test fixture/i) // title = raw first segment (prod quirk)
    expect(done.source).toBe('desktop')
    expect((done.transcript_segments as unknown[])?.length).toBe(segments.length)
    // started_at/finished_at round-trip — the exact property the outbox dedupe
    // and list reconcile rely on.
    expect(Math.abs(Date.parse(String(done.started_at)) - sessionStart)).toBeLessThan(2_000)
    expect(Math.abs(Date.parse(String(done.finished_at)) - endedAt)).toBeLessThan(2_000)

    // ---- 5. The unconfirmed-dedupe rule finds it in the REAL list -----------
    const list = await listConversations()
    const match = findCloudMatch(
      { startedAt: sessionStart, endedAt, segmentCount: segments.length },
      list as Array<{ id: string; started_at?: string | null; finished_at?: string | null }>
    )
    expect(match, 'findCloudMatch locates our conversation in the live list').toBe(createdId)

    // ---- 6. Delete (only after completed) and verify by re-list -------------
    const del = await axios.delete(`${OMI_BASE}/v1/conversations/${createdId}`, {
      ...api(),
      validateStatus: () => true
    })
    console.log(`[conv-sync-e2e] DELETE → ${del.status}`)
    expect([200, 204]).toContain(del.status)
    const after = await listConversations()
    expect(after.some((c) => c.id === createdId), 'deleted conversation gone from re-list').toBe(false)
    deletedVerified = true
  }, 300_000)
})
