import { ipcMain, WebContents, webContents } from 'electron'
import WebSocket from 'ws'
import type {
  BackendSegment,
  ListenEvent,
  ListenMessage,
  ListenStartArgs
} from '../../shared/types'

function buildEndpoint(language: string): string {
  return (
    'wss://api.omi.me/v4/listen' +
    `?language=${encodeURIComponent(language || 'en')}` +
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
    try { existing.ws.close() } catch { /* ignore */ }
    sessions.delete(args.sessionId)
  }
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
  const base = buildEndpoint(args.language)
  const url = uid ? `${base}&uid=${encodeURIComponent(uid)}` : base
  const ws = new WebSocket(url, {
    headers: { Authorization: `Bearer ${args.token}` }
  })
  ws.binaryType = 'arraybuffer'
  const session: Session = { ws, ownerId: owner.id, source: args.source, closed: false }
  sessions.set(args.sessionId, session)

  ws.on('open', () => {
    emit(session.ownerId, { sessionId: args.sessionId, kind: 'connected' })
  })

  ws.on('message', (data, isBinary) => {
    if (isBinary) return // v4/listen sends text only; ignore stray binary
    const text = data.toString().trim()
    if (text === 'ping' || text === '') return
    let json: unknown
    try {
      json = JSON.parse(text)
    } catch {
      return
    }
    if (Array.isArray(json)) {
      emit(session.ownerId, {
        sessionId: args.sessionId,
        kind: 'segments',
        segments: json as BackendSegment[]
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
    emit(session.ownerId, {
      sessionId: args.sessionId,
      kind: 'closed',
      code,
      reason: reasonBuf.toString()
    })
  })
}

function feedSession(sessionId: string, pcm: ArrayBuffer): void {
  const s = sessions.get(sessionId)
  if (!s || s.ws.readyState !== WebSocket.OPEN) return
  s.ws.send(pcm)
}

function stopSession(sessionId: string): void {
  const s = sessions.get(sessionId)
  if (!s) return
  s.closed = true
  sessions.delete(sessionId)
  try { s.ws.close() } catch { /* ignore */ }
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
}
