// src/main/ipc/deepgramListen.ts
// Deepgram Live Transcription via WebSocket
import { ipcMain, WebContents, webContents } from 'electron'
import WebSocket from 'ws'
import https from 'https'
import { translateToGlosses, defaultSignOpts } from '../integrations/signLanguage'
import type { BackendSegment, ListenEvent, ListenMessage, ListenStartArgs } from '../../shared/types'

const DEEPGRAM_WS_URL = 'wss://api.deepgram.com/v1/listen'

type DeepgramSession = {
  ws: WebSocket
  ownerId: number
  source: 'mic' | 'system'
  closed: boolean
  startTime: number
  buffer: ArrayBuffer[]
  transcriptBuffer: string
  lastTranslationTime: number
  keepalive?: ReturnType<typeof setInterval>
}

const sessions = new Map<string, DeepgramSession>()

function emit(ownerId: number, msg: ListenMessage): void {
  const wc = webContents.fromId(ownerId)
  if (wc && !wc.isDestroyed()) {
    wc.send('omi-listen:message', msg)
  }
}

// Test API key with a simple REST request
function testApiKey(apiKey: string): Promise<{ ok: boolean; error?: string }> {
  return new Promise((resolve) => {
    const req = https.request(
      {
        hostname: 'api.deepgram.com',
        path: '/v1/projects',
        method: 'GET',
        headers: {
          Authorization: `Token ${apiKey}`
        },
        timeout: 10000
      },
      (res) => {
        let body = ''
        res.on('data', (chunk) => (body += chunk))
        res.on('end', () => {
          if (res.statusCode === 200) {
            console.log('[deepgram] API key valid')
            resolve({ ok: true })
          } else {
            console.error(`[deepgram] API key test failed: ${res.statusCode} ${body}`)
            resolve({ ok: false, error: `HTTP ${res.statusCode}: ${body}` })
          }
        })
      }
    )
    req.on('error', (err) => {
      console.error(`[deepgram] API key test error:`, err.message)
      resolve({ ok: false, error: err.message })
    })
    req.on('timeout', () => {
      req.destroy()
      resolve({ ok: false, error: 'Connection timeout' })
    })
    req.end()
  })
}

function buildDeepgramUrl(language: string): string {
  const params = new URLSearchParams({
    model: 'nova-2',
    encoding: 'linear16',
    sample_rate: '16000',
    channels: '1',
    interim_results: 'true',
    speech_final: 'true',
    utterance_end_ms: '1000',
    sentiment: 'true',
    // Speaker diarization: assigns an ephemeral cluster id to each speaker so we
    // can tell "me" apart from other people in the room.
    diarize: 'true'
  })
  if (language && language !== 'en') {
    params.set('language', language)
  }
  return `${DEEPGRAM_WS_URL}?${params.toString()}`
}

function startDeepgramSession(args: ListenStartArgs, owner: WebContents, apiKey: string): void {
  const existing = sessions.get(args.sessionId)
  if (existing) {
    try { existing.ws.close() } catch { /* ignore */ }
    sessions.delete(args.sessionId)
  }

  const url = buildDeepgramUrl(args.language)
  console.log(`[deepgram] connecting to: ${url}`)
  console.log(`[deepgram] API key: ${apiKey.substring(0, 8)}...${apiKey.substring(apiKey.length - 4)}`)

  const ws = new WebSocket(url, {
    headers: {
      Authorization: `Token ${apiKey}`
    },
    handshakeTimeout: 10000
  })
  ws.binaryType = 'arraybuffer'

  const session: DeepgramSession = {
    ws,
    ownerId: owner.id,
    source: args.source,
    closed: false,
    startTime: Date.now(),
    buffer: [],
    transcriptBuffer: '',
    lastTranslationTime: 0
  }
  sessions.set(args.sessionId, session)

  ws.on('open', () => {
    console.log(`[deepgram] session ${args.sessionId} connected, flushing ${session.buffer.length} buffered chunks`)
    emit(session.ownerId, { sessionId: args.sessionId, kind: 'connected' })
    // Flush buffered audio
    for (const chunk of session.buffer) {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(chunk)
      }
    }
    session.buffer = []
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

    const obj = json as Record<string, unknown>
    const type = obj.type as string | undefined

    // Handle transcript results
    if (obj.channel && typeof obj.channel === 'object') {
      const channel = obj.channel as Record<string, unknown>
      const alternatives = channel.alternatives as Array<{ transcript: string; confidence: number }> | undefined
      if (alternatives && alternatives.length > 0) {
        const alt = alternatives[0]
        if (alt.transcript && alt.transcript.trim()) {
          const duration = (obj.duration as number) || 0
          const start = (obj.start as number) || 0

          // Extract sentiment if present
          const sentiment = obj.sentiment as { sentiment: string; confidence: number } | undefined

          // Diarization: pick the dominant speaker cluster for this utterance from
          // the per-word `speaker` labels Deepgram attaches when diarize=true.
          const words = (alt as { words?: Array<{ speaker?: number }> }).words
          let speakerId: number | undefined
          if (words && words.length > 0) {
            const counts = new Map<number, number>()
            for (const w of words) {
              if (typeof w.speaker === 'number') {
                counts.set(w.speaker, (counts.get(w.speaker) ?? 0) + 1)
              }
            }
            let best = -1
            let bestN = 0
            for (const [id, n] of counts) {
              if (n > bestN) {
                bestN = n
                best = id
              }
            }
            if (best >= 0) speakerId = best
          }

          const segment: BackendSegment = {
            id: `dg-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
            text: alt.transcript,
            // is_user is resolved in the renderer against the enrolled voiceprint;
            // we pass the cluster id and a provisional label. Default to true only
            // when no diarization info is available (single-speaker fallback).
            is_user: speakerId == null,
            ...(speakerId != null ? { speaker_id: speakerId, speaker: `Speaker ${speakerId}` } : {}),
            start: Math.round(start * 1000),
            end: Math.round((start + duration) * 1000),
            ...(sentiment ? { sentiment: sentiment.sentiment, sentimentScore: sentiment.confidence } : {})
          }

          emit(session.ownerId, {
            sessionId: args.sessionId,
            kind: 'segments',
            segments: [segment]
          })

          // --- Live Sign Language Translation ---
          const isFinal = (obj as any).is_final === true;
          const transcript = alt.transcript.trim();
          
          if (isFinal) {
            session.transcriptBuffer += (session.transcriptBuffer ? ' ' : '') + transcript;
          }

          // Translate if it's a final segment, or if we've accumulated enough text 
          // and it's been a while since the last translation.
          const now = Date.now();
          const shouldTranslate = isFinal || (session.transcriptBuffer.length > 10 && now - session.lastTranslationTime > 2000);

          if (shouldTranslate) {
            const fullText = isFinal 
              ? session.transcriptBuffer 
              : (session.transcriptBuffer + (isFinal ? '' : ' ' + transcript)).trim();
            
            const textToTranslate = fullText.slice(-256); // Send only the most recent 256 chars
            
            if (textToTranslate) {
              translateToGlosses(textToTranslate, 'en', 'ase', defaultSignOpts()).then(result => {
                const wc = webContents.fromId(session.ownerId);
                if (wc && !wc.isDestroyed()) {
                  wc.send('omi-sign-update', result);
                }
              }).catch(e => console.error('[deepgram] live translation failed:', e));
              
              session.lastTranslationTime = now;
              if (isFinal) {
                // We don't clear the buffer immediately to maintain context for the next segment,
                // but we might want to truncate it if it gets too long.
                if (session.transcriptBuffer.length > 1000) {
                  session.transcriptBuffer = session.transcriptBuffer.slice(-500);
                }
              }
            }
          }
          if (!isFinal) {
            // For interim results, we can still update the buffer if we want, 
            // but we typically rely on is_final for stable translation.
          }
          return
        }
      }
      return
    }


    // Handle utterance end
    if (type === 'UtteranceEnd') {
      const event: ListenEvent = { type: 'utterance_end', raw: obj }
      emit(session.ownerId, { sessionId: args.sessionId, kind: 'event', event })
      return
    }

    // Handle speech started/stopped
    if (type === 'SpeechStarted' || type === 'SpeakStarted') {
      const event: ListenEvent = { type: type.toLowerCase(), raw: obj }
      emit(session.ownerId, { sessionId: args.sessionId, kind: 'event', event })
      return
    }

    // Handle error
    if (type === 'Error') {
      const message = (obj.message as string) || 'Deepgram error'
      emit(session.ownerId, {
        sessionId: args.sessionId,
        kind: 'error',
        message,
        fatal: true
      })
      return
    }
  })

  ws.on('error', (err) => {
    console.error(`[deepgram] session ${args.sessionId} error:`, err.message)
    console.error(`[deepgram] full error:`, err)
    emit(session.ownerId, {
      sessionId: args.sessionId,
      kind: 'error',
      message: `Deepgram: ${err.message}`,
      fatal: ws.readyState !== WebSocket.OPEN
    })
  })

  ws.on('close', (code, reasonBuf) => {
    if (session.closed) return
    session.closed = true
    if (session.keepalive) clearInterval(session.keepalive)
    sessions.delete(args.sessionId)
    console.log(`[deepgram] session ${args.sessionId} closed (${code}) reason=${reasonBuf.toString()}`)
    emit(session.ownerId, {
      sessionId: args.sessionId,
      kind: 'closed',
      code,
      reason: reasonBuf.toString()
    })
  })
}

let feedLogCount = 0

function feedSession(sessionId: string, pcm: ArrayBuffer): void {
  const s = sessions.get(sessionId)
  if (!s || s.closed) {
    feedLogCount++
    if (feedLogCount <= 5 || feedLogCount % 200 === 0) {
      console.log(`[deepgram] feed dropped: session=${sessionId} exists=${!!s} closed=${s?.closed}`)
    }
    return
  }
  if (s.ws.readyState !== WebSocket.OPEN) {
    s.buffer.push(pcm)
    if (s.buffer.length <= 3 || s.buffer.length % 50 === 0) {
      console.log(`[deepgram] buffering: ${s.buffer.length} chunks pending`)
    }
    if (s.buffer.length > 200) s.buffer.shift()
    return
  }
  s.ws.send(pcm)
  feedLogCount++
  if (feedLogCount <= 3 || feedLogCount % 200 === 0) {
    console.log(`[deepgram] feed #${feedLogCount}: ${pcm.byteLength} bytes sent`)
  }
}

function stopSession(sessionId: string): void {
  const s = sessions.get(sessionId)
  if (!s) return
  s.closed = true
  sessions.delete(sessionId)
  try { s.ws.close(1000, 'client close') } catch { /* ignore */ }
}

let deepgramApiKey = ''

export function setDeepgramApiKey(key: string): void {
  deepgramApiKey = key
}

export function getDeepgramApiKey(): string {
  return deepgramApiKey
}

export function registerDeepgramListenHandlers(): void {
  // Test API key before starting session
  ipcMain.handle('deepgram-listen:testKey', async () => {
    if (!deepgramApiKey) return { ok: false, error: 'No API key configured' }
    return testApiKey(deepgramApiKey)
  })

  ipcMain.handle('deepgram-listen:start', (e, args: ListenStartArgs) => {
    if (!deepgramApiKey) {
      console.warn('[deepgram] no API key configured')
      emit(e.sender.id, {
        sessionId: args.sessionId,
        kind: 'error',
        message: 'Deepgram API key not configured',
        fatal: true
      })
      return
    }
    startDeepgramSession(args, e.sender, deepgramApiKey)
  })

  ipcMain.handle('deepgram-listen:stop', (_e, sessionId: string) => {
    stopSession(sessionId)
  })

  ipcMain.on('deepgram-listen:feed', (_e, sessionId: string, pcm: ArrayBuffer) => {
    feedSession(sessionId, pcm)
  })
}
