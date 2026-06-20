import { afterEach, describe, expect, it } from 'vitest'
import { WebSocketServer } from 'ws'
import type { AddressInfo } from 'net'
import type { BackendSegment } from '../../shared/types'
import { normalizeParakeetSegment, ParakeetStreamSession } from './parakeetSession'

const servers: WebSocketServer[] = []

afterEach(async () => {
  await Promise.all(
    servers.splice(0).map(
      (server) =>
        new Promise<void>((resolve) => {
          server.close(() => resolve())
        })
    )
  )
})

describe('Parakeet segment normalization', () => {
  it('maps local mic segments into the shared backend segment shape', () => {
    const segment = normalizeParakeetSegment({
      raw: {
        text: ' hello world ',
        speaker: 'SPEAKER_2',
        start: 1.25,
        end: 2.5,
        person_id: 'person-1'
      },
      source: 'mic',
      sessionId: 's1',
      sequence: 3,
      fallbackStart: 0
    })

    expect(segment).toEqual({
      id: 'local-s1-3',
      text: 'hello world',
      speaker: 'SPEAKER_2',
      speaker_id: 2,
      is_user: true,
      person_id: 'person-1',
      start: 1.25,
      end: 2.5
    })
  })

  it('drops empty transcripts and repairs invalid timing', () => {
    expect(
      normalizeParakeetSegment({
        raw: { text: '   ', start: 1, end: 2 },
        source: 'system',
        sessionId: 's1',
        sequence: 1,
        fallbackStart: 0
      })
    ).toBeNull()

    expect(
      normalizeParakeetSegment({
        raw: { text: 'tail', start: 4, end: 3 },
        source: 'system',
        sessionId: 's1',
        sequence: 2,
        fallbackStart: 10
      })
    ).toMatchObject({ text: 'tail', is_user: false, start: 4, end: 4.01 })
  })

  it('streams PCM to a Parakeet-compatible WebSocket and flushes on stop', async () => {
    const server = new WebSocketServer({ port: 0 })
    servers.push(server)
    await new Promise<void>((resolve) => server.once('listening', () => resolve()))
    const port = (server.address() as AddressInfo).port
    let sawPcm = false
    let sawFinalize = false

    server.on('connection', (ws) => {
      ws.on('message', (data, isBinary) => {
        if (isBinary) {
          sawPcm = true
          return
        }
        if (data.toString() === 'finalize') {
          sawFinalize = true
          ws.send(JSON.stringify({ text: 'local words', speaker: 'SPEAKER_0', start: 0, end: 1 }))
          ws.close(1000, 'done')
        }
      })
    })

    const emitted: BackendSegment[][] = []
    const session = new ParakeetStreamSession({
      sessionId: 'runtime',
      source: 'mic',
      baseUrl: `http://127.0.0.1:${port}`,
      handlers: {
        onConnected: () => undefined,
        onSegments: (segments) => emitted.push(segments),
        onError: (message) => {
          throw new Error(message)
        },
        onClosed: () => undefined
      }
    })

    await session.start()
    session.feed(new Int16Array([1, 2, 3, 4]).buffer)
    await session.stop()

    expect(sawPcm).toBe(true)
    expect(sawFinalize).toBe(true)
    expect(emitted).toEqual([
      [
        {
          id: 'local-runtime-1',
          text: 'local words',
          speaker: 'SPEAKER_0',
          speaker_id: 0,
          is_user: true,
          person_id: undefined,
          start: 0,
          end: 1
        }
      ]
    ])
  })
})
