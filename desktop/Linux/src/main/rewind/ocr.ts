import { spawn, ChildProcessWithoutNullStreams } from 'child_process'
import { createInterface } from 'readline'
import { resourcePath } from '../resources'

// Linux counterpart of Apple Vision OCR: a persistent sidecar running under
// Electron's bundled Node (ELECTRON_RUN_AS_NODE=1) that shells out to the
// Tesseract CLI (resources/ocr-worker.cjs). Same one-path-per-line / one-JSON-
// result-per-line protocol as the Windows PowerShell worker, so the queue and
// handshake logic below is unchanged.

interface Job {
  path: string
  resolve: (text: string | null) => void
}

class OcrService {
  private proc: ChildProcessWithoutNullStreams | null = null
  private queue: Job[] = []
  private inFlight: Job | null = null
  private ready = false
  private failedPermanently = false

  get pending(): number {
    return this.queue.length + (this.inFlight ? 1 : 0)
  }

  private scriptPath(): string {
    return resourcePath('ocr-worker.cjs')
  }

  private ensureProcess(): void {
    if (this.proc || this.failedPermanently) return
    const proc = spawn(
      process.execPath,
      [this.scriptPath()],
      { env: { ...process.env, ELECTRON_RUN_AS_NODE: '1' }, stdio: 'pipe' }
    )
    this.proc = proc
    const rl = createInterface({ input: proc.stdout })
    rl.on('line', (line) => this.handleLine(line))
    proc.stderr.on('data', () => {})
    proc.stdin.on('error', (err) => {
      console.error('ocr: worker stdin failed:', err)
      this.proc = null
      this.ready = false
      this.drainAll(null)
    })
    proc.on('error', (err) => {
      console.error('ocr: worker failed to start:', err)
      this.proc = null
      this.ready = false
      this.drainAll(null)
    })
    proc.on('exit', () => {
      this.proc = null
      this.ready = false
      // Fail the in-flight job; the queue is restarted lazily on the next
      // recognize() call (which respawns the sidecar). Resolve any jobs that
      // are already queued so their promises never hang on a hard crash.
      this.inFlight?.resolve(null)
      this.inFlight = null
      for (const j of this.queue.splice(0)) j.resolve(null)
    })
  }

  private handleLine(line: string): void {
    let parsed: { ok: boolean; ready?: boolean; fatal?: boolean; text?: string; error?: string }
    try {
      parsed = JSON.parse(line)
    } catch {
      return
    }
    if (parsed.ready) {
      this.ready = true
      this.pump()
      return
    }
    if (parsed.fatal) {
      this.failedPermanently = true
      console.error('ocr: engine unavailable:', parsed.error)
      this.drainAll(null)
      return
    }
    const job = this.inFlight
    this.inFlight = null
    job?.resolve(parsed.ok ? (parsed.text ?? '') : null)
    this.pump()
  }

  private drainAll(result: string | null): void {
    this.inFlight?.resolve(result)
    this.inFlight = null
    for (const j of this.queue.splice(0)) j.resolve(result)
  }

  private pump(): void {
    if (this.inFlight || !this.proc || !this.ready) return
    const job = this.queue.shift()
    if (!job) return
    this.inFlight = job
    this.proc.stdin.write(job.path + '\n')
  }

  recognize(path: string): Promise<string | null> {
    if (this.failedPermanently) return Promise.resolve(null)
    this.ensureProcess()
    return new Promise((resolve) => {
      this.queue.push({ path, resolve })
      this.pump()
    })
  }

  dispose(): void {
    this.drainAll(null)
    this.proc?.kill()
    this.proc = null
  }
}

export const ocrService = new OcrService()
