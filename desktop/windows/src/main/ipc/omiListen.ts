import { ipcMain, WebContents, webContents } from 'electron'
import WebSocket from 'ws'
import type {
  BackendSegment,
  ListenEvent,
  ListenMessage,
  ListenMode,
  ListenStartArgs
} from '../../shared/types'

/**
 * Build the WebSocket endpoint for a listen session by mode.
 *
 * - 'conversation' → `/v4/listen`: the full pipeline (speech profiles, speaker
 *   assignment, memory events) that keeps a per-uid server-side conversation.
 *   Used for continuous recording. Codec `pcm16`.
 * - 'ptt' → `/v2/voice-message/transcribe-stream`: transcription-only, NO
 *   conversation lifecycle — so separate hold-to-talk captures never share state
 *   (an earlier hold's speech can't bleed into the next). Mirrors the macOS `.ptt`
 *   mode. NOTE: this endpoint requires `codec=linear16` (it rejects `pcm16` with a
 *   1008 close); linear16 is the same little-endian PCM16 bytes we already send,
 *   just the name the endpoint expects.
 *
 * The caller appends `&uid=` for conversation mode only (PTT is header-auth only).
 */
export function buildListenEndpoint(mode: ListenMode, language: string): string {
  const lang = encodeURIComponent(language || 'en')
  if (mode === 'ptt') {
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
}

const sessions = new Map<string, Session>()

function emit(ownerId: number, msg: ListenMessage): void {
  const wc = webContents.fromId(ownerId)
  if (wc && !wc.isDestroyed()) {
    wc.send('omi-listen:message', msg)
  }
}

function startSession(args: ListenStartArgs, owner: WebContents): void {
  const existing = sessions.get(args.sessionId)
  if (existing) {
    // Already running — caller bug. Tear the old one down to avoid leaks.
    try {
      existing.ws.close()
    } catch {
      /* ignore */
    }
    sessions.delete(args.sessionId)
  }
  const mode: ListenMode = args.mode ?? 'conversation'

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
  const session: Session = { ws, ownerId: owner.id, source: args.source, mode, closed: false }
  sessions.set(args.sessionId, session)
  console.log(`[omi-listen] start ${args.sessionId} mode=${mode} source=${args.source}`)

  ws.on('open', () => {
    console.log(`[omi-listen] connected ${args.sessionId} mode=${mode}`)
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
    console.log(`[omi-listen] error ${args.sessionId} mode=${mode}: ${err.message}`)
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
  if (!s || s.ws.readyState !== WebSocket.OPEN) return
  s.ws.send(pcm)
}

/**
 * PTT-only: ask the transcribe-stream backend to flush buffered audio and finalize
 * Deepgram so the trailing segment is emitted promptly (~0.3s), instead of waiting
 * out silence. A text frame the backend recognizes; harmless no-op mid-session on
 * the conversation endpoint (v4/listen ignores unknown text), but we only send it
 * for PTT sessions.
 */
function finalizeSession(sessionId: string): void {
  const s = sessions.get(sessionId)
  if (!s || s.mode !== 'ptt' || s.ws.readyState !== WebSocket.OPEN) return
  console.log(`[omi-listen] finalize ${sessionId}`)
  try {
    s.ws.send('finalize')
  } catch {
    /* ignore */
  }
}

function stopSession(sessionId: string): void {
  const s = sessions.get(sessionId)
  if (!s) return
  s.closed = true
  sessions.delete(sessionId)
  try {
    s.ws.close()
  } catch {
    /* ignore */
  }
}

export function registerOmiListenHandlers(): void {
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
