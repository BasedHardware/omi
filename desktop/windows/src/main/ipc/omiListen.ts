import { ipcMain, WebContents, webContents } from 'electron'
import WebSocket from 'ws'
import type {
  BackendSegment,
  ListenEvent,
  ListenMessage,
  ListenStartArgs
} from '../../shared/types'
import { loadByokKey } from '../byok/store'
import { ParakeetCppSession } from '../localStt/parakeetCppSession'
import {
  ensureManagedParakeetRuntime,
  type ManagedParakeetRuntime
} from '../localStt/parakeetCppRuntime'
import { getLocalSttStatus } from '../localStt/status'

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
  backend: 'omi' | 'local-parakeet' | 'elevenlabs'
  ws?: WebSocket
  local?: ParakeetCppSession
  ownerId: number // webContents id for routing replies back
  source: 'mic' | 'system'
  closed: boolean
  segmentSeq?: number
}

const sessions = new Map<string, Session>()

function emit(ownerId: number, msg: ListenMessage): void {
  const wc = webContents.fromId(ownerId)
  if (wc && !wc.isDestroyed()) {
    wc.send('omi-listen:message', msg)
  }
}

async function stopSession(sessionId: string): Promise<void> {
  const s = sessions.get(sessionId)
  if (!s) return
  s.closed = true
  sessions.delete(sessionId)
  if (s.backend === 'local-parakeet' && s.local) {
    await s.local.stop()
    return
  }
  try {
    s.ws?.close()
  } catch {
    /* ignore */
  }
}

async function startSession(args: ListenStartArgs, owner: WebContents): Promise<void> {
  const existing = sessions.get(args.sessionId)
  if (existing) {
    // Already running — caller bug. Tear the old one down to avoid leaks.
    await stopSession(args.sessionId)
  }

  const mode = args.sttMode ?? 'auto'
  if (mode === 'elevenlabs') {
    startElevenLabsSession(args, owner)
    return
  }
  if (mode === 'local-parakeet' || mode === 'auto') {
    const status = await getLocalSttStatus()
    if (status.available || status.runtime.canInstall) {
      try {
        if (!status.available) {
          emit(owner.id, {
            sessionId: args.sessionId,
            kind: 'event',
            event: {
              type: 'local_stt_installing',
              raw: { runtime: status.runtime.kind, model: status.runtime.model }
            }
          })
        }
        const runtime = await ensureManagedParakeetRuntime()
        await startLocalSession(args, owner, runtime, mode === 'auto')
      } catch (err) {
        const message = err instanceof Error ? err.message : 'local Parakeet STT unavailable'
        if (mode === 'auto') {
          emit(owner.id, {
            sessionId: args.sessionId,
            kind: 'event',
            event: { type: 'local_stt_fallback_cloud', raw: { reason: message } }
          })
          startCloudSession(args, owner)
          return
        }
        emit(owner.id, { sessionId: args.sessionId, kind: 'error', message, fatal: true })
      }
      return
    } else if (mode === 'local-parakeet') {
      emit(owner.id, {
        sessionId: args.sessionId,
        kind: 'error',
        message: status.reason ?? 'local Parakeet STT unavailable',
        fatal: true
      })
      return
    }
  }

  startCloudSession(args, owner)
}

async function startLocalSession(
  args: ListenStartArgs,
  owner: WebContents,
  runtime: ManagedParakeetRuntime,
  fallbackCloudOnStartupFailure: boolean
): Promise<void> {
  const session: Session = {
    backend: 'local-parakeet',
    ownerId: owner.id,
    source: args.source,
    closed: false
  }
  const local = new ParakeetCppSession({
    sessionId: args.sessionId,
    source: args.source,
    language: args.language,
    runtime,
    handlers: {
      onConnected: () => {
        emit(session.ownerId, {
          sessionId: args.sessionId,
          kind: 'connected',
          backend: 'local-parakeet'
        })
      },
      onSegments: (segments) => {
        emit(session.ownerId, { sessionId: args.sessionId, kind: 'segments', segments })
      },
      onError: (message, fatal) => {
        emit(session.ownerId, { sessionId: args.sessionId, kind: 'error', message, fatal })
      },
      onClosed: (code, reason) => {
        if (session.closed) return
        session.closed = true
        sessions.delete(args.sessionId)
        emit(session.ownerId, { sessionId: args.sessionId, kind: 'closed', code, reason })
      }
    }
  })
  session.local = local
  sessions.set(args.sessionId, session)
  await local.start().catch((err) => {
    if (session.closed) return
    sessions.delete(args.sessionId)
    session.closed = true
    if (fallbackCloudOnStartupFailure) {
      emit(session.ownerId, {
        sessionId: args.sessionId,
        kind: 'event',
        event: { type: 'local_stt_fallback_cloud', raw: { reason: (err as Error).message } }
      })
      startCloudSession(args, owner)
      return
    }
    emit(session.ownerId, {
      sessionId: args.sessionId,
      kind: 'error',
      message: (err as Error).message,
      fatal: true
    })
  })
}

function buildElevenLabsEndpoint(language: string): string {
  const params = new URLSearchParams({
    model_id: process.env.OMI_ELEVENLABS_STT_MODEL || 'scribe_v2_realtime',
    audio_format: 'pcm_16000',
    commit_strategy: 'vad',
    include_timestamps: 'false'
  })
  if (language) params.set('language_code', language)
  return `wss://api.elevenlabs.io/v1/speech-to-text/realtime?${params.toString()}`
}

function elevenLabsSegment(session: Session, sessionId: string, text: string): BackendSegment {
  const now = Date.now() / 1000
  session.segmentSeq = (session.segmentSeq ?? 0) + 1
  return {
    id: `elevenlabs-${sessionId}-${session.segmentSeq}`,
    text,
    is_user: session.source === 'mic',
    speaker: session.source === 'mic' ? 'You' : 'System',
    start: now,
    end: now
  }
}

function elevenLabsErrorMessage(raw: Record<string, unknown>): string {
  const message = raw.message ?? raw.error ?? raw.detail
  return typeof message === 'string' && message.trim()
    ? message.trim()
    : String(raw.message_type ?? 'ElevenLabs STT error')
}

function startElevenLabsSession(args: ListenStartArgs, owner: WebContents): void {
  const key = loadByokKey('elevenlabs')
  if (!key) {
    emit(owner.id, {
      sessionId: args.sessionId,
      kind: 'error',
      message: 'Save an ElevenLabs key before using ElevenLabs STT',
      fatal: true
    })
    return
  }

  const ws = new WebSocket(buildElevenLabsEndpoint(args.language), {
    headers: { 'xi-api-key': key }
  })
  const session: Session = {
    backend: 'elevenlabs',
    ws,
    ownerId: owner.id,
    source: args.source,
    closed: false,
    segmentSeq: 0
  }
  sessions.set(args.sessionId, session)

  ws.on('open', () => {
    emit(session.ownerId, {
      sessionId: args.sessionId,
      kind: 'event',
      event: { type: 'elevenlabs_stt_socket_open', raw: {} }
    })
  })

  ws.on('message', (data, isBinary) => {
    if (isBinary) return
    const text = data.toString().trim()
    if (!text) return
    let json: unknown
    try {
      json = JSON.parse(text)
    } catch {
      return
    }
    if (!json || typeof json !== 'object') return
    const obj = json as Record<string, unknown>
    const messageType = String(obj.message_type ?? obj.type ?? '')
    if (messageType === 'session_started') {
      emit(session.ownerId, {
        sessionId: args.sessionId,
        kind: 'connected',
        backend: 'elevenlabs'
      })
      return
    }
    if (messageType === 'partial_transcript') {
      emit(session.ownerId, {
        sessionId: args.sessionId,
        kind: 'event',
        event: { type: 'elevenlabs_partial_transcript', raw: obj }
      })
      return
    }
    if (
      messageType === 'committed_transcript' ||
      messageType === 'committed_transcript_with_timestamps'
    ) {
      const committed = typeof obj.text === 'string' ? obj.text.trim() : ''
      if (!committed) return
      emit(session.ownerId, {
        sessionId: args.sessionId,
        kind: 'segments',
        segments: [elevenLabsSegment(session, args.sessionId, committed)]
      })
      return
    }
    if (
      messageType.toLowerCase().includes('error') ||
      messageType.toLowerCase().includes('quota')
    ) {
      emit(session.ownerId, {
        sessionId: args.sessionId,
        kind: 'error',
        message: elevenLabsErrorMessage(obj),
        fatal: true
      })
      return
    }
    if (messageType) {
      emit(session.ownerId, {
        sessionId: args.sessionId,
        kind: 'event',
        event: { type: messageType, raw: obj }
      })
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

function startCloudSession(args: ListenStartArgs, owner: WebContents): void {
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
  const session: Session = {
    backend: 'omi',
    ws,
    ownerId: owner.id,
    source: args.source,
    closed: false
  }
  sessions.set(args.sessionId, session)

  ws.on('open', () => {
    emit(session.ownerId, { sessionId: args.sessionId, kind: 'connected', backend: 'omi' })
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
  if (!s) return
  if (s.backend === 'local-parakeet') {
    s.local?.feed(pcm)
    return
  }
  if (s.ws?.readyState !== WebSocket.OPEN) return
  if (s.backend === 'elevenlabs') {
    s.ws.send(
      JSON.stringify({
        message_type: 'input_audio_chunk',
        audio_base_64: Buffer.from(pcm).toString('base64'),
        sample_rate: 16000
      })
    )
    return
  }
  s.ws.send(pcm)
}

export function registerOmiListenHandlers(): void {
  ipcMain.handle('omi-listen:start', async (e, args: ListenStartArgs) => {
    await startSession(args, e.sender)
  })
  ipcMain.handle('omi-listen:stop', async (_e, sessionId: string) => {
    await stopSession(sessionId)
  })
  ipcMain.handle('omi-local-stt:status', async () => {
    return getLocalSttStatus()
  })
  // `on` (not `handle`) — feed is fire-and-forget to keep audio throughput cheap.
  ipcMain.on('omi-listen:feed', (_e, sessionId: string, pcm: ArrayBuffer) => {
    feedSession(sessionId, pcm)
  })
}
