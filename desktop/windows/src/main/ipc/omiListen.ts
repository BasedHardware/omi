import { ipcMain, WebContents, webContents } from 'electron'
import WebSocket from 'ws'
import {
  PCM_PENDING_MAX_BYTES,
  type BackendSegment,
  type ListenEvent,
  type ListenMessage,
  type ListenMode,
  type ListenStartArgs
} from '../../shared/types'

/**
 * Build the WebSocket endpoint for a listen session by mode.
 *
 * - 'conversation' → `/v4/listen`: the full pipeline (speech profiles, speaker
 *   assignment, memory events) that keeps a per-uid server-side conversation.
 *   Used for continuous MIC-ONLY recording. Codec `pcm16`.
 * - 'ptt' and 'transcribe' → `/v2/voice-message/transcribe-stream`:
 *   transcription-only, NO conversation lifecycle. 'ptt' is the overlay's
 *   hold-to-talk (separate holds never share state — an earlier hold's speech
 *   can't bleed into the next; mirrors the macOS `.ptt` mode). 'transcribe' is
 *   the same endpoint for SCREEN-session lanes (mic + system): two /v4/listen
 *   sockets from one uid coalesce via a racy user-global Redis pointer (verified
 *   splitting/bleeding on prod), so screen lanes stream transcription-only and
 *   the client creates the conversation on stop via from-segments. The distinct
 *   mode value keeps PTT's supersede logic from killing screen sessions.
 *   NOTE: this endpoint requires `codec=linear16` (it rejects `pcm16` with a
 *   1008 close); linear16 is the same little-endian PCM16 bytes we already send,
 *   just the name the endpoint expects.
 *
 * The caller appends `&uid=` for conversation mode only (PTT is header-auth only).
 */
export function buildListenEndpoint(mode: ListenMode, language: string): string {
  const lang = encodeURIComponent(language || 'en')
  if (mode === 'ptt' || mode === 'transcribe') {
    return (
      'wss://api.omi.me/v2/voice-message/transcribe-stream' +
      `?language=${lang}` +
      '&sample_rate=16000' +
      '&codec=linear16' +
      '&channels=1'
    )
  }
  return (
    'wss://api.omi.me/v4/listen' +
    `?language=${lang}` +
    '&sample_rate=16000' +
    '&codec=pcm16' +
    '&channels=1' +
    '&include_speech_profile=true' +
    '&source=desktop' +
    '&speaker_auto_assign=enabled'
  )
}

type Session = {
  ws: WebSocket
  ownerId: number // webContents id for routing replies back
  source: 'mic' | 'system'
  mode: ListenMode
  closed: boolean
  // Audio captured before the socket reaches OPEN. The renderer starts streaming
  // PCM the moment the mic is live, but the WS handshake can take a beat (esp. PTT
  // transcribe-stream under load). Without this, a quick hold ("hello") is spoken
  // and released before OPEN, so every chunk is dropped and nothing transcribes.
  // We buffer those pre-OPEN chunks (bounded) and flush them on 'open'.
  pending: Buffer[]
  pendingBytes: number
}

const sessions = new Map<string, Session>()

// Verification counters — monotonic bytes/chunks the renderer has fed per
// `${mode}:${source}`, read by the soak + VAD-playback harnesses via
// getListenStats(). Post-gate audio only (the renderer's VAD gate drops silence
// before feeding), so a flat byte delta across a silent interval proves gating.
// Never reset within a process.
const listenStats = new Map<string, { bytes: number; chunks: number }>()

function recordFed(mode: ListenMode, source: 'mic' | 'system', bytes: number): void {
  const key = `${mode}:${source}`
  const cur = listenStats.get(key) ?? { bytes: 0, chunks: 0 }
  cur.bytes += bytes
  cur.chunks += 1
  listenStats.set(key, cur)
}

/** OMI_E2E only: register a socketless counting session so the VAD-playback
 * harness can assert post-gate byte flow with zero auth/network. feedSession
 * counts via recordFed then drops the bytes (stub is never OPEN/CONNECTING). */
export function startTestListenSession(sessionId: string, source: 'mic' | 'system'): boolean {
  if (process.env.OMI_E2E !== '1') return false
  const stub = {
    readyState: 3, // CLOSED — feedSession counts, then neither sends nor buffers
    close(): void {
      /* no socket */
    },
    send(): void {
      /* no socket */
    }
  } as unknown as WebSocket
  sessions.set(sessionId, {
    ws: stub,
    ownerId: -1,
    source,
    mode: 'conversation',
    closed: false,
    pending: [],
    pendingBytes: 0
  })
  return true
}

export function stopTestListenSession(sessionId: string): void {
  const s = sessions.get(sessionId)
  if (!s) return
  s.closed = true
  sessions.delete(sessionId)
}

/** Snapshot of bytes/chunks fed per mode:source since process start. */
export function getListenStats(): Record<string, { bytes: number; chunks: number }> {
  const out: Record<string, { bytes: number; chunks: number }> = {}
  for (const [k, v] of listenStats) out[k] = { bytes: v.bytes, chunks: v.chunks }
  return out
}

function emit(ownerId: number, msg: ListenMessage): void {
  const wc = webContents.fromId(ownerId)
  if (wc && !wc.isDestroyed()) {
    wc.send('omi-listen:message', msg)
  }
}

/** The one way a session dies early: mark closed, drop buffers, remove from the
 *  map, close the socket. Shared by replace/supersede/stop so Session cleanup
 *  can't drift between call sites. */
function killSession(id: string, s: Session, why: string): void {
  console.log(`[omi-listen] ${why} ${id} mode=${s.mode} (readyState=${s.ws.readyState})`)
  s.closed = true
  s.pending = []
  s.pendingBytes = 0
  sessions.delete(id)
  try {
    s.ws.close()
  } catch {
    /* ignore */
  }
}

function startSession(args: ListenStartArgs, owner: WebContents): void {
  const existing = sessions.get(args.sessionId)
  if (existing) {
    // Already running under the same id — caller bug; tear down to avoid leaks.
    killSession(args.sessionId, existing, 'replace')
  }
  const mode: ListenMode = args.mode ?? 'conversation'

  // Push-to-talk is a single-at-a-time gesture. When a new PTT hold opens its
  // connection, close any prior PTT session for the same window — a rapid series of
  // holds otherwise leaves several connections handshaking to the same endpoint at
  // once, and they contend (connect times balloon from ~100ms to 4-11s). The
  // superseded hold is NOT lost: its renderer job keeps its locally-retained
  // buffer, sees the stream death, and falls back to batch transcription.
  if (mode === 'ptt') {
    for (const [id, s] of sessions) {
      if (id !== args.sessionId && s.mode === 'ptt' && s.ownerId === owner.id) {
        killSession(id, s, `supersede (new PTT hold ${args.sessionId})`)
      }
    }
  }

  const base = buildListenEndpoint(mode, args.language)
  let url = base
  if (mode === 'conversation') {
    // Decode (not verify) the JWT to derive the uid for the query param; the
    // backend verifies the token from the Authorization header.
    let uid = ''
    try {
      const payload = JSON.parse(
        Buffer.from(args.token.split('.')[1] ?? '', 'base64').toString('utf8')
      )
      uid = payload.user_id ?? payload.sub ?? ''
    } catch {
      // Token not decodable; uid stays empty (the backend also reads the
      // Authorization header).
    }
    // Official docs require `uid` as a query param; backend source also reads the
    // Firebase token from the Authorization header. Send both.
    if (uid) url = `${base}&uid=${encodeURIComponent(uid)}`
  }
  // PTT is header-auth only (no uid query param, matching the macOS client) since
  // there's no per-uid conversation to key.

  const ws = new WebSocket(url, {
    headers: { Authorization: `Bearer ${args.token}` }
  })
  ws.binaryType = 'arraybuffer'
  const session: Session = {
    ws,
    ownerId: owner.id,
    source: args.source,
    mode,
    closed: false,
    pending: [],
    pendingBytes: 0
  }
  sessions.set(args.sessionId, session)
  const t0 = Date.now()
  console.log(`[omi-listen] start ${args.sessionId} mode=${mode} source=${args.source}`)

  ws.on('open', () => {
    console.log(`[omi-listen] connected ${args.sessionId} mode=${mode} in ${Date.now() - t0}ms`)
    // Flush audio captured while the handshake was in flight, in order, so speech
    // spoken during the connect window (e.g. a quick "hello") isn't lost.
    if (session.pending.length > 0) {
      console.log(
        `[omi-listen] flush ${args.sessionId} ${session.pending.length} pre-connect chunk(s) (${session.pendingBytes}B)`
      )
      for (const chunk of session.pending) {
        try {
          ws.send(chunk)
        } catch {
          /* ignore */
        }
      }
      session.pending = []
      session.pendingBytes = 0
    }
    emit(session.ownerId, { sessionId: args.sessionId, kind: 'connected' })
  })

  ws.on('message', (data, isBinary) => {
    if (isBinary) return // both endpoints send text only; ignore stray binary
    const text = data.toString().trim()
    if (text === 'ping' || text === '') return
    let json: unknown
    try {
      json = JSON.parse(text)
    } catch {
      return
    }
    if (Array.isArray(json)) {
      const segments = json as BackendSegment[]
      console.log(`[omi-listen] segments ${args.sessionId} mode=${mode} count=${segments.length}`)
      emit(session.ownerId, {
        sessionId: args.sessionId,
        kind: 'segments',
        segments
      })
      return
    }
    if (json && typeof json === 'object' && 'type' in (json as object)) {
      const obj = json as Record<string, unknown>
      const event: ListenEvent = { type: String(obj.type), raw: obj }
      emit(session.ownerId, { sessionId: args.sessionId, kind: 'event', event })
    }
  })

  ws.on('error', (err) => {
    console.log(
      `[omi-listen] error ${args.sessionId} mode=${mode} after ${Date.now() - t0}ms (readyState=${ws.readyState}): ${err.message}`
    )
    emit(session.ownerId, {
      sessionId: args.sessionId,
      kind: 'error',
      message: err.message,
      fatal: ws.readyState !== WebSocket.OPEN
    })
  })

  ws.on('close', (code, reasonBuf) => {
    if (session.closed) return
    session.closed = true
    sessions.delete(args.sessionId)
    const reason = reasonBuf.toString()
    console.log(
      `[omi-listen] closed ${args.sessionId} mode=${mode} code=${code}${reason ? ` reason=${reason}` : ''}`
    )
    emit(session.ownerId, {
      sessionId: args.sessionId,
      kind: 'closed',
      code,
      reason
    })
  })
}

function feedSession(sessionId: string, pcm: ArrayBuffer): void {
  const s = sessions.get(sessionId)
  if (!s) return
  recordFed(s.mode, s.source, pcm.byteLength)
  if (s.ws.readyState === WebSocket.OPEN) {
    s.ws.send(pcm)
    return
  }
  // Still connecting (or closing): buffer so pre-OPEN speech isn't dropped. Once
  // OPEN the 'open' handler flushes these. Bounded — drop oldest past the cap.
  if (s.ws.readyState === WebSocket.CONNECTING) {
    const chunk = Buffer.from(pcm)
    s.pending.push(chunk)
    s.pendingBytes += chunk.byteLength
    while (s.pendingBytes > PCM_PENDING_MAX_BYTES && s.pending.length > 1) {
      const dropped = s.pending.shift()!
      s.pendingBytes -= dropped.byteLength
    }
  }
}

/**
 * Transcribe-stream sessions only ('ptt'/'transcribe'): ask the backend to flush
 * buffered audio and finalize Deepgram so the trailing segment is emitted promptly
 * (~0.3s), instead of waiting out silence. PTT CONTRACT: the renderer only calls
 * this after it has observed the 'connected' message — a hold released while still
 * connecting skips the stream lane entirely and batch-transcribes its
 * locally-retained buffer instead, so a not-OPEN call here is simply a no-op.
 * Screen sessions ('transcribe') call it at stop so trailing speech lands before
 * the lanes are merged; a never-connected lane is likewise a no-op.
 */
function finalizeSession(sessionId: string): void {
  const s = sessions.get(sessionId)
  if (!s || s.mode === 'conversation' || s.ws.readyState !== WebSocket.OPEN) return
  console.log(`[omi-listen] finalize ${sessionId}`)
  try {
    s.ws.send('finalize')
  } catch {
    /* ignore */
  }
}

function stopSession(sessionId: string): void {
  const s = sessions.get(sessionId)
  if (s) killSession(sessionId, s, 'stop')
}

export function registerOmiListenHandlers(): void {
  // Expose the byte counters to the E2E harnesses (VAD-playback / soak) so a
  // Playwright electronApp.evaluate can read them from the main process. Gated on
  // OMI_E2E — inert in production.
  if (process.env.OMI_E2E === '1') {
    ;(globalThis as Record<string, unknown>).__omiGetListenStats = getListenStats
  }
  ipcMain.handle('omi-listen:start', (e, args: ListenStartArgs) => {
    startSession(args, e.sender)
  })
  ipcMain.handle('omi-listen:stop', (_e, sessionId: string) => {
    stopSession(sessionId)
  })
  // `on` (not `handle`) — feed is fire-and-forget to keep audio throughput cheap.
  ipcMain.on('omi-listen:feed', (_e, sessionId: string, pcm: ArrayBuffer) => {
    feedSession(sessionId, pcm)
  })
  ipcMain.on('omi-listen:finalize', (_e, sessionId: string) => {
    finalizeSession(sessionId)
  })
}
