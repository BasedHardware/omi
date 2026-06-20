import { randomUUID } from 'crypto'
import { spawn } from 'child_process'
import { mkdir, rm, writeFile } from 'fs/promises'
import { tmpdir } from 'os'
import { join } from 'path'
import type { BackendSegment, ListenSource } from '../../shared/types'
import { normalizeParakeetSegment } from './parakeetSession'
import {
  noteManagedParakeetSessionStarted,
  noteManagedParakeetSessionStopped,
  type ManagedParakeetRuntime
} from './parakeetCppRuntime'

const SAMPLE_RATE = 16000
const BYTES_PER_SAMPLE = 2
const DEFAULT_DRAIN_SECONDS = 10
const MIN_FINAL_SECONDS = 0.25
const CLI_TIMEOUT_MS = 2 * 60_000

type CliSegment = Record<string, unknown>

type ParakeetCppHandlers = {
  onConnected: () => void
  onSegments: (segments: BackendSegment[]) => void
  onError: (message: string, fatal: boolean) => void
  onClosed: (code: number, reason: string) => void
}

type RunCli = (wavPath: string) => Promise<string>

export function writePcm16Wav(path: string, pcm: Buffer, sampleRate = SAMPLE_RATE): Promise<void> {
  const header = Buffer.alloc(44)
  const byteRate = sampleRate * BYTES_PER_SAMPLE
  const blockAlign = BYTES_PER_SAMPLE

  header.write('RIFF', 0)
  header.writeUInt32LE(36 + pcm.length, 4)
  header.write('WAVE', 8)
  header.write('fmt ', 12)
  header.writeUInt32LE(16, 16)
  header.writeUInt16LE(1, 20)
  header.writeUInt16LE(1, 22)
  header.writeUInt32LE(sampleRate, 24)
  header.writeUInt32LE(byteRate, 28)
  header.writeUInt16LE(blockAlign, 32)
  header.writeUInt16LE(16, 34)
  header.write('data', 36)
  header.writeUInt32LE(pcm.length, 40)

  return writeFile(path, Buffer.concat([header, pcm]))
}

export function parseParakeetCliOutput(stdout: string): CliSegment[] {
  const text = stdout.trim()
  if (!text) return []

  const parsed = parseJsonPayload(text)
  if (parsed !== null) return cliSegmentsFromPayload(parsed)

  const lines = text
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
  const lineSegments = lines.flatMap((line) => {
    const payload = parseJsonPayload(line)
    return payload === null ? [] : cliSegmentsFromPayload(payload)
  })
  if (lineSegments.length > 0) return lineSegments

  return [{ text }]
}

export class ParakeetCppSession {
  private readonly drainBytes: number
  private readonly tmpRoot: string
  private buffers: Buffer[] = []
  private bufferedBytes = 0
  private closed = false
  private sequence = 0
  private lastEnd = 0
  private offsetSeconds = 0
  private timer: NodeJS.Timeout | null = null
  private drainPromise: Promise<void> = Promise.resolve()
  private stopPromise: Promise<void> | null = null

  constructor(
    private readonly args: {
      sessionId: string
      source: ListenSource
      language: string
      runtime: ManagedParakeetRuntime
      handlers: ParakeetCppHandlers
      drainSeconds?: number
      runCli?: RunCli
      tmpRoot?: string
    }
  ) {
    this.drainBytes =
      Math.max(1, args.drainSeconds ?? DEFAULT_DRAIN_SECONDS) * SAMPLE_RATE * BYTES_PER_SAMPLE
    this.tmpRoot = args.tmpRoot ?? join(tmpdir(), 'omi-local-stt')
  }

  async start(): Promise<void> {
    if (this.closed) throw new Error('local Parakeet session already closed')
    noteManagedParakeetSessionStarted()
    this.args.handlers.onConnected()
    this.timer = setInterval(() => {
      void this.queueDrain(false)
    }, 1000)
    this.timer.unref?.()
  }

  feed(pcm: ArrayBuffer): void {
    if (this.closed) return
    const chunk = Buffer.from(new Uint8Array(pcm))
    if (chunk.length === 0) return
    this.buffers.push(chunk)
    this.bufferedBytes += chunk.length
    if (this.bufferedBytes >= this.drainBytes) {
      void this.queueDrain(false)
    }
  }

  async stop(): Promise<void> {
    if (this.stopPromise) return this.stopPromise
    this.stopPromise = this.stopInner()
    return this.stopPromise
  }

  private async stopInner(): Promise<void> {
    this.closed = true
    if (this.timer) clearInterval(this.timer)
    await this.queueDrain(true)
    noteManagedParakeetSessionStopped()
    this.args.handlers.onClosed(1000, 'done')
  }

  private queueDrain(final: boolean): Promise<void> {
    const run = async (): Promise<void> => {
      try {
        await this.drainAvailable(final)
      } catch (err) {
        const message = err instanceof Error ? err.message : String(err)
        this.args.handlers.onError(message, false)
      }
    }
    this.drainPromise = this.drainPromise.then(run, run)
    return this.drainPromise
  }

  private async drainAvailable(final: boolean): Promise<void> {
    while (this.bufferedBytes >= this.drainBytes) {
      await this.drainChunk(this.drainBytes)
    }

    if (final && this.bufferedBytes >= MIN_FINAL_SECONDS * SAMPLE_RATE * BYTES_PER_SAMPLE) {
      await this.drainChunk(this.bufferedBytes)
    }
  }

  private async drainChunk(byteCount: number): Promise<void> {
    const pcm = this.takeBytes(byteCount)
    const durationSeconds = pcm.length / BYTES_PER_SAMPLE / SAMPLE_RATE
    const wavPath = join(this.tmpRoot, `${this.args.sessionId}-${randomUUID()}.wav`)

    try {
      await mkdir(this.tmpRoot, { recursive: true })
      await writePcm16Wav(wavPath, pcm)
      const stdout = await (this.args.runCli ?? this.runCli.bind(this))(wavPath)
      const segments = this.toBackendSegments(parseParakeetCliOutput(stdout), durationSeconds)
      if (segments.length > 0) this.args.handlers.onSegments(segments)
    } finally {
      await rm(wavPath, { force: true })
      this.offsetSeconds += durationSeconds
    }
  }

  private takeBytes(byteCount: number): Buffer {
    const out = Buffer.alloc(byteCount)
    let offset = 0

    while (offset < byteCount) {
      const next = this.buffers[0]
      const remaining = byteCount - offset
      if (next.length <= remaining) {
        next.copy(out, offset)
        offset += next.length
        this.buffers.shift()
      } else {
        next.copy(out, offset, 0, remaining)
        this.buffers[0] = next.subarray(remaining)
        offset += remaining
      }
    }

    this.bufferedBytes -= byteCount
    return out
  }

  private toBackendSegments(rawSegments: CliSegment[], durationSeconds: number): BackendSegment[] {
    const segments: BackendSegment[] = []
    for (const raw of rawSegments) {
      const start =
        typeof raw.start === 'number' && Number.isFinite(raw.start)
          ? this.offsetSeconds + raw.start
          : this.lastEnd
      const end =
        typeof raw.end === 'number' && Number.isFinite(raw.end)
          ? this.offsetSeconds + raw.end
          : this.offsetSeconds + durationSeconds
      const segment = normalizeParakeetSegment({
        raw: {
          ...raw,
          start,
          end
        },
        source: this.args.source,
        sessionId: this.args.sessionId,
        sequence: ++this.sequence,
        fallbackStart: this.lastEnd
      })
      if (!segment) continue
      this.lastEnd = Math.max(this.lastEnd, segment.end)
      segments.push(segment)
    }
    return segments
  }

  private runCli(wavPath: string): Promise<string> {
    const cliArgs = [
      'transcribe',
      '--model',
      this.args.runtime.modelPath,
      '--input',
      wavPath,
      '--decoder',
      'tdt',
      '--json',
      '--timestamps'
    ]
    if (this.args.language) {
      cliArgs.push('--lang', this.args.language)
    }
    return runProcess(this.args.runtime.exePath, cliArgs, CLI_TIMEOUT_MS)
  }
}

function parseJsonPayload(text: string): unknown | null {
  try {
    return JSON.parse(text)
  } catch {
    return null
  }
}

function cliSegmentsFromPayload(payload: unknown): CliSegment[] {
  if (typeof payload === 'string') return [{ text: payload }]
  if (Array.isArray(payload)) return payload.flatMap(cliSegmentsFromPayload)
  if (!payload || typeof payload !== 'object') return []

  const record = payload as Record<string, unknown>
  for (const key of ['segments', 'results', 'transcripts']) {
    if (Array.isArray(record[key])) return cliSegmentsFromPayload(record[key])
  }

  const text = firstString(record.text, record.transcript, record.transcription)
  if (!text) return []

  const words = Array.isArray(record.words) ? record.words : []
  const wordTimes = words
    .filter((word): word is Record<string, unknown> => Boolean(word) && typeof word === 'object')
    .map((word) => ({
      start: numberValue(word.start ?? word.start_time),
      end: numberValue(word.end ?? word.end_time)
    }))
    .filter((word) => word.start != null || word.end != null)

  const start =
    numberValue(record.start ?? record.start_time) ??
    minDefined(wordTimes.map((word) => word.start)) ??
    undefined
  const end =
    numberValue(record.end ?? record.end_time) ??
    maxDefined(wordTimes.map((word) => word.end)) ??
    undefined

  return [{ ...record, text, start, end }]
}

function firstString(...values: unknown[]): string | null {
  for (const value of values) {
    if (typeof value === 'string' && value.trim()) return value.trim()
  }
  return null
}

function numberValue(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function minDefined(values: Array<number | null>): number | null {
  const nums = values.filter((value): value is number => value != null)
  return nums.length > 0 ? Math.min(...nums) : null
}

function maxDefined(values: Array<number | null>): number | null {
  const nums = values.filter((value): value is number => value != null)
  return nums.length > 0 ? Math.max(...nums) : null
}

async function runProcess(command: string, args: string[], timeoutMs: number): Promise<string> {
  return new Promise<string>((resolve, reject) => {
    const child = spawn(command, args, { windowsHide: true })
    const stdout: Buffer[] = []
    let stderr = ''
    const timer = setTimeout(() => {
      try {
        child.kill()
      } catch {
        /* ignore */
      }
      reject(new Error(`${command} timed out`))
    }, timeoutMs)
    timer.unref?.()

    child.stdout.on('data', (data) => {
      stdout.push(Buffer.from(data))
    })
    child.stderr.on('data', (data) => {
      stderr += data.toString()
    })
    child.on('error', (err) => {
      clearTimeout(timer)
      reject(err)
    })
    child.on('close', (code) => {
      clearTimeout(timer)
      if (code === 0) {
        resolve(Buffer.concat(stdout).toString('utf8'))
        return
      }
      reject(new Error(stderr.trim() || `${command} exited with code ${code ?? 'unknown'}`))
    })
  })
}
