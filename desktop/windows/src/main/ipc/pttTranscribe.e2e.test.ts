/**
 * End-to-end harness for the PTT transcription backends — the REAL network paths
 * the push-to-talk feature rides: the batch REST endpoint
 * (`POST /v2/voice-message/transcribe`) and the streaming WebSocket
 * (`wss://…/v2/voice-message/transcribe-stream`), driven with real synthesized
 * speech (see scripts/gen-audio-fixtures.mjs).
 *
 * It proves what the unit tests can't: actual transcripts come back, actual
 * latencies fit the app's deadlines (the finalize→segment budget below IS the
 * app's 3s stream deadline — if that fails here, the app would be falling back
 * to batch in practice), and the failure modes (silence, bad auth) behave as the
 * client design assumes. An `afterAll` prints a latency report table.
 *
 * GATED on auth and skips entirely without it, so it never runs in `pnpm test`:
 *
 *   # Option A (1-hour token): in the running app's devtools →
 *   #   await auth.currentUser.getIdToken()
 *   $env:OMI_E2E_TOKEN="<id-token>"
 *   # Option B (unattended, recommended): put OMI_E2E_REFRESH_TOKEN=<refresh token>
 *   #   in desktop/windows/.env — grab it via the IndexedDB snippet documented in
 *   #   scripts/diag-listen-probe.mjs. The suite exchanges it for a fresh ID token
 *   #   per run via securetoken.googleapis.com (needs VITE_FIREBASE_API_KEY, already
 *   #   in .env).
 *   pnpm test:e2e:ptt            # generates fixtures if missing, runs this file
 *
 * Budget note: the full suite costs ~9 requests of the account's 60/hour
 * `voice:transcribe` budget and a few seconds of its 2h/day audio budget.
 */
import { execFileSync } from 'node:child_process'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import axios from 'axios'
import WebSocket from 'ws'
import { describe, it, expect, beforeAll, afterAll } from 'vitest'
import { buildListenEndpoint } from './omiListen'

const HERE = path.dirname(fileURLToPath(import.meta.url))

// ---------------------------------------------------------------------------
// Env / gating
// ---------------------------------------------------------------------------
function readDotEnv(): Record<string, string> {
  const envPath = path.resolve(HERE, '../../../.env')
  const out: Record<string, string> = {}
  try {
    for (const line of fs.readFileSync(envPath, 'utf8').split(/\r?\n/)) {
      const m = line.match(/^([A-Z0-9_]+)=(.*)$/)
      if (m) out[m[1]] = m[2].trim()
    }
  } catch {
    /* no .env — env vars only */
  }
  return out
}
const dotEnv = readDotEnv()
const DIRECT_TOKEN = process.env.OMI_E2E_TOKEN ?? dotEnv.OMI_E2E_TOKEN ?? ''
const REFRESH_TOKEN =
  process.env.OMI_E2E_REFRESH_TOKEN ??
  dotEnv.OMI_E2E_REFRESH_TOKEN ??
  // The diag probe historically stored it under this name — accept both.
  process.env.OMI_REFRESH_TOKEN ??
  dotEnv.OMI_REFRESH_TOKEN ??
  ''
const FIREBASE_API_KEY = process.env.VITE_FIREBASE_API_KEY ?? dotEnv.VITE_FIREBASE_API_KEY ?? ''
const OMI_BASE = process.env.VITE_OMI_API_BASE ?? dotEnv.VITE_OMI_API_BASE ?? 'https://api.omi.me'

const FIXTURE_DIR = path.resolve(HERE, '../../../test/fixtures/audio')

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
let idToken = ''

async function resolveIdToken(): Promise<string> {
  if (DIRECT_TOKEN) return DIRECT_TOKEN
  if (!FIREBASE_API_KEY) throw new Error('VITE_FIREBASE_API_KEY missing (needed for refresh-token exchange)')
  const res = await axios.post(
    `https://securetoken.googleapis.com/v1/token?key=${FIREBASE_API_KEY}`,
    new URLSearchParams({ grant_type: 'refresh_token', refresh_token: REFRESH_TOKEN }),
    { headers: { 'Content-Type': 'application/x-www-form-urlencoded' }, timeout: 15_000 }
  )
  return res.data.id_token as string
}

function fixture(name: string): Buffer {
  return fs.readFileSync(path.join(FIXTURE_DIR, name))
}

function batchUrl(): string {
  return `${OMI_BASE}/v2/voice-message/transcribe?language=en&sample_rate=16000&encoding=linear16&channels=1`
}

function streamUrl(): string {
  // The production URL builder, with the host swapped when OMI_BASE overrides prod.
  const url = buildListenEndpoint('ptt', 'en')
  const wsBase = OMI_BASE.replace(/^http/, 'ws')
  return url.replace('wss://api.omi.me', wsBase)
}

async function postBatch(
  pcm: Buffer,
  token = idToken
): Promise<{ status: number; body: { transcript?: string; language?: string }; ms: number }> {
  const t0 = Date.now()
  const res = await axios.post(batchUrl(), pcm, {
    headers: { 'Content-Type': 'application/octet-stream', Authorization: `Bearer ${token}` },
    timeout: 30_000,
    validateStatus: () => true
  })
  return { status: res.status, body: res.data ?? {}, ms: Date.now() - t0 }
}

type StreamResult = {
  connected: boolean
  connectMs: number
  finalizeToSegmentMs: number
  segments: string[]
  closeCode: number | null
}

/**
 * Drive a real transcribe-stream session the way the app's main process does:
 * binary PCM frames, then the text frame 'finalize', then collect segment arrays.
 * `feedInOpenHandler` reproduces the release-before-connect shape: ALL audio +
 * finalize queued the moment the socket opens (byte-for-byte what omiListen.ts
 * does when the hold was released while still CONNECTING).
 */
function streamSession(
  pcm: Buffer,
  opts: { paceMs?: number; chunkBytes?: number; idleBeforeFeedMs?: number } = {}
): Promise<StreamResult> {
  const { paceMs = 0, chunkBytes = 8192, idleBeforeFeedMs = 0 } = opts
  return new Promise((resolve, reject) => {
    const t0 = Date.now()
    const ws = new WebSocket(streamUrl(), { headers: { Authorization: `Bearer ${idToken}` } })
    const result: StreamResult = {
      connected: false,
      connectMs: -1,
      finalizeToSegmentMs: -1,
      segments: [],
      closeCode: null
    }
    let tFinalize = 0
    const deadline = setTimeout(() => finish(), 20_000)
    const finish = (): void => {
      clearTimeout(deadline)
      try {
        ws.terminate()
      } catch {
        /* closed */
      }
      resolve(result)
    }
    ws.on('open', () => {
      result.connected = true
      result.connectMs = Date.now() - t0
      void (async () => {
        if (idleBeforeFeedMs > 0) await new Promise((r) => setTimeout(r, idleBeforeFeedMs))
        for (let off = 0; off < pcm.length; off += chunkBytes) {
          ws.send(pcm.subarray(off, off + chunkBytes))
          if (paceMs > 0) await new Promise((r) => setTimeout(r, paceMs))
        }
        tFinalize = Date.now()
        ws.send('finalize')
        // Give the trailing segment a bounded window, then finish.
        setTimeout(finish, 8_000)
      })()
    })
    ws.on('message', (data, isBinary) => {
      if (isBinary) return
      const text = data.toString().trim()
      if (!text || text === 'ping') return
      try {
        const json = JSON.parse(text)
        if (Array.isArray(json)) {
          const texts = json.map((s: { text?: string }) => s.text ?? '').filter(Boolean)
          if (texts.length > 0) {
            result.segments.push(...texts)
            if (tFinalize > 0 && result.finalizeToSegmentMs < 0) {
              result.finalizeToSegmentMs = Date.now() - tFinalize
            }
          }
        }
      } catch {
        /* non-JSON frame */
      }
    })
    ws.on('close', (code) => {
      result.closeCode = code
      finish()
    })
    ws.on('unexpected-response', (_req, res) => {
      reject(new Error(`unexpected-response HTTP ${res.statusCode}`))
    })
    ws.on('error', (err) => {
      if (!result.connected) reject(err)
    })
  })
}

// Latency report ------------------------------------------------------------
const metrics: Array<{ name: string; ms: number; budgetMs: number }> = []
function recordMetric(name: string, ms: number, budgetMs: number): void {
  metrics.push({ name, ms, budgetMs })
  expect(ms, `${name}: ${ms}ms exceeded budget ${budgetMs}ms`).toBeLessThan(budgetMs)
}

// ---------------------------------------------------------------------------
// Suite
// ---------------------------------------------------------------------------
describe.skipIf(!DIRECT_TOKEN && !REFRESH_TOKEN)('ptt transcription e2e (live api.omi.me)', () => {
  beforeAll(async () => {
    if (!fs.existsSync(path.join(FIXTURE_DIR, 'manifest.json'))) {
      execFileSync('node', [path.resolve(HERE, '../../../scripts/gen-audio-fixtures.mjs')], {
        stdio: 'inherit',
        timeout: 180_000
      })
    }
    idToken = await resolveIdToken()
    const payload = JSON.parse(Buffer.from(idToken.split('.')[1], 'base64url').toString('utf8'))
    console.log(
      `[ptt-e2e] uid=${payload.user_id ?? payload.sub} exp=${new Date(payload.exp * 1000).toISOString()} base=${OMI_BASE}`
    )
  }, 120_000)

  afterAll(() => {
    if (metrics.length === 0) return
    const w = Math.max(...metrics.map((m) => m.name.length)) + 2
    console.log(`\n=== PTT LATENCY REPORT (${OMI_BASE}, en, 16kHz) ===`)
    console.log(`  ${'metric'.padEnd(w)}${'actual'.padStart(8)}${'budget'.padStart(9)}  verdict`)
    for (const m of metrics) {
      console.log(
        `  ${m.name.padEnd(w)}${`${m.ms}ms`.padStart(8)}${`${m.budgetMs}ms`.padStart(9)}  ${m.ms < m.budgetMs ? 'PASS' : 'FAIL'}`
      )
    }
  })

  it('batch: real speech transcribes with expected words', async () => {
    const { status, body, ms } = await postBatch(fixture('speech-hello.pcm'))
    expect(status).toBe(200)
    expect(body.transcript ?? '').toMatch(/hello/i)
    expect(body.transcript ?? '').toMatch(/world/i)
    console.log(`[ptt-e2e] batch transcript: ${JSON.stringify(body.transcript)} (${ms}ms)`)
    recordMetric('batch POST ~3.8s utterance', ms, 8_000)
  }, 40_000)

  it('batch: long utterance (~80s) transcribes', async () => {
    const { status, body, ms } = await postBatch(fixture('speech-long.pcm'))
    expect(status).toBe(200)
    expect((body.transcript ?? '').length).toBeGreaterThan(100)
    recordMetric('batch POST ~80s utterance', ms, 20_000)
  }, 40_000)

  it('stream: happy path — connect, paced feed, finalize, segment', async () => {
    const r = await streamSession(fixture('speech-hello.pcm'), { paceMs: 100 })
    expect(r.connected).toBe(true)
    expect(r.segments.length).toBeGreaterThan(0)
    expect(r.segments.join(' ')).toMatch(/hello/i)
    recordMetric('WS connect (open)', r.connectMs, 6_000)
    // The app's stream deadline: a finalize→segment slower than 3s means the app
    // would batch-fallback in practice.
    recordMetric('finalize -> first segment', r.finalizeToSegmentMs, 3_000)
  }, 40_000)

  it('stream: release-before-connect (all audio + finalize queued at open)', async () => {
    const t0 = Date.now()
    const r = await streamSession(fixture('speech-hello.pcm'))
    expect(r.connected).toBe(true)
    // Burst-fed audio can degrade STT diction slightly (observed: "Health world"
    // for "Hello world") — the invariant is that a transcript ARRIVES despite
    // finalize being queued at open, so assert on "world", not "hello".
    expect(r.segments.join(' ')).toMatch(/world/i)
    recordMetric('release-before-connect end-to-end', Date.now() - t0, 12_000)
  }, 40_000)

  it('batch: 5 rapid-fire sequential requests all succeed', async () => {
    const times: number[] = []
    for (let i = 0; i < 5; i++) {
      const { status, ms } = await postBatch(fixture('speech-short-200ms.pcm'))
      expect(status, `request ${i + 1} status`).toBe(200)
      times.push(ms)
    }
    times.sort((a, b) => a - b)
    console.log(`[ptt-e2e] rapid-fire times: ${times.join(', ')}ms`)
    recordMetric('rapid-fire p95 (5x 200ms clip)', times[times.length - 1], 8_000)
  }, 60_000)

  it('batch: silence — hallucination probe (documents why the client gates)', async () => {
    const { status, body } = await postBatch(fixture('silence-2s.pcm'))
    expect(status).toBe(200)
    const transcript = body.transcript ?? ''
    console.log(`[ptt-e2e] silence transcript: ${JSON.stringify(transcript)}`)
    if (transcript.trim()) {
      console.warn(
        `[ptt-e2e] ⚠ backend transcribed SILENCE as ${JSON.stringify(transcript)} — this is the STT hallucination the client-side voiced gate must prevent from ever being sent`
      )
    }
  }, 40_000)

  it('batch: quiet speech — documents what the RMS gate discards', async () => {
    const { status, body } = await postBatch(fixture('speech-quiet.pcm'))
    expect(status).toBe(200)
    console.log(`[ptt-e2e] quiet-speech transcript: ${JSON.stringify(body.transcript ?? '')}`)
  }, 40_000)

  it('batch: bogus token is rejected', async () => {
    const { status } = await postBatch(fixture('speech-short-200ms.pcm'), 'bogus-token')
    expect([401, 403]).toContain(status)
  }, 40_000)

  it('stream: bogus token never opens', async () => {
    await expect(
      new Promise((resolve, reject) => {
        const ws = new WebSocket(streamUrl(), { headers: { Authorization: 'Bearer bogus' } })
        const t = setTimeout(() => {
          ws.terminate()
          reject(new Error('timed out without open/close'))
        }, 10_000)
        ws.on('open', () => {
          // Backends may accept the upgrade then close 1008 — treat a quick
          // policy close as rejection too (below).
        })
        ws.on('close', (code) => {
          clearTimeout(t)
          code === 1008 ? resolve(code) : reject(new Error(`unexpected close ${code}`))
        })
        ws.on('unexpected-response', (_req, res) => {
          clearTimeout(t)
          ;[401, 403].includes(res.statusCode ?? 0)
            ? resolve(res.statusCode)
            : reject(new Error(`unexpected HTTP ${res.statusCode}`))
        })
        ws.on('error', () => {
          /* swallowed — close/unexpected-response decide */
        })
      })
    ).resolves.toBeTruthy()
  }, 20_000)

  it('stream: socket survives a 3s idle hold before audio (opportunistic-lane stability)', async () => {
    const r = await streamSession(fixture('speech-short-200ms.pcm'), { idleBeforeFeedMs: 3_000 })
    expect(r.connected).toBe(true)
    // The point is the socket did not get idle-killed before we fed audio; a
    // transcript for a 200ms clip is not guaranteed.
    expect(r.closeCode === null || r.closeCode === 1000 || r.closeCode === 1005).toBe(true)
  }, 40_000)
})
