import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { mkdtemp, readFile, rm } from 'fs/promises'
import { join } from 'path'
import { tmpdir } from 'os'
import type { BackendSegment } from '../../shared/types'
import { parseParakeetCliOutput, ParakeetCppSession, writePcm16Wav } from './parakeetCppSession'
import { resetManagedParakeetRuntimeStateForTests } from './parakeetCppRuntime'

let root = ''

beforeEach(async () => {
  resetManagedParakeetRuntimeStateForTests()
  root = await mkdtemp(join(tmpdir(), 'omi-parakeet-session-'))
})

afterEach(async () => {
  resetManagedParakeetRuntimeStateForTests()
  if (root) await rm(root, { recursive: true, force: true })
  root = ''
})

describe('parakeet.cpp CLI session', () => {
  it('writes PCM16 WAV files with a valid header', async () => {
    const wav = join(root, 'sample.wav')
    await writePcm16Wav(wav, Buffer.from(new Int16Array([1, -2, 3]).buffer))

    const bytes = await readFile(wav)
    expect(bytes.subarray(0, 4).toString('ascii')).toBe('RIFF')
    expect(bytes.subarray(8, 12).toString('ascii')).toBe('WAVE')
    expect(bytes.readUInt32LE(40)).toBe(6)
  })

  it('parses JSON output shapes from parakeet.cpp', () => {
    expect(
      parseParakeetCliOutput(
        JSON.stringify({
          text: 'hello world',
          words: [
            { start: 0.1, end: 0.2 },
            { start: 0.3, end: 0.8 }
          ]
        })
      )
    ).toEqual([
      {
        text: 'hello world',
        words: [
          { start: 0.1, end: 0.2 },
          { start: 0.3, end: 0.8 }
        ],
        start: 0.1,
        end: 0.8
      }
    ])

    expect(parseParakeetCliOutput('plain transcript')).toEqual([{ text: 'plain transcript' }])
  })

  it('flushes buffered PCM through the CLI and emits backend segments', async () => {
    const emitted: BackendSegment[][] = []
    let wavHeader = ''
    const session = new ParakeetCppSession({
      sessionId: 'runtime',
      source: 'mic',
      language: 'en',
      drainSeconds: 10,
      tmpRoot: root,
      runtime: {
        exePath: 'parakeet-cli.exe',
        modelPath: 'model.gguf',
        runtimeRoot: root,
        variant: 'cuda',
        model: 'tdt_ctc-110m-q8_0.gguf',
        version: 'v0.3.2'
      },
      runCli: async (wavPath) => {
        wavHeader = (await readFile(wavPath)).subarray(0, 4).toString('ascii')
        return JSON.stringify({
          text: 'local words',
          words: [
            { start: 0.1, end: 0.3 },
            { start: 0.35, end: 0.9 }
          ]
        })
      },
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
    session.feed(new Int16Array(16000).buffer)
    await session.stop()

    expect(wavHeader).toBe('RIFF')
    expect(emitted).toEqual([
      [
        {
          id: 'local-runtime-1',
          text: 'local words',
          speaker: undefined,
          speaker_id: undefined,
          is_user: true,
          person_id: undefined,
          start: 0.1,
          end: 0.9
        }
      ]
    ])
  })
})
