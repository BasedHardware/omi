import { spawn, type ChildProcessWithoutNullStreams } from 'child_process'
import { resolveHelperPath } from './resolveHelperPath'
import { encodeRequest, FrameDecoder, OP_OCR, OP_WINDOW } from './helperProtocol'
import type { OcrResult, WindowInfo } from '../../shared/types'

const REQUEST_TIMEOUT_MS = 5000
const MAX_BACKOFF_MS = 10000

type Pending = {
  resolve: (json: string) => void
  reject: (e: Error) => void
  timer: NodeJS.Timeout
}

/**
 * One supervised, long-running helper process shared by OCR + window-info.
 * Lazy start; capped-backoff restart on crash; single-flight FIFO request queue
 * (the helper processes one frame at a time, so we serialize). Per-request
 * timeout recycles the process to avoid a wedged pipe blocking forever.
 */
class HelperProcess {
  private child: ChildProcessWithoutNullStreams | null = null
  private readonly queue: Pending[] = []
  private backoff = 500
  private starting = false
  // Set once the helper binary is confirmed missing (spawn ENOENT). Without this,
  // every OCR/window request re-spawns the missing exe, failing forever — flooding
  // the log and stalling each caller on a doomed spawn. Once unavailable, fail fast.
  private unavailable = false

  private ensureStarted(): void {
    if (this.child || this.starting || this.unavailable) return
    this.starting = true
    const exe = resolveHelperPath()
    const child = spawn(exe, [], { stdio: ['pipe', 'pipe', 'pipe'] })
    this.child = child
    this.starting = false

    const decoder = new FrameDecoder((json) => {
      const pending = this.queue.shift()
      if (!pending) return
      clearTimeout(pending.timer)
      pending.resolve(json)
    })
    child.stdout.on('data', (chunk: Buffer) => decoder.push(chunk))
    child.stderr.on('data', (c: Buffer) => console.log('[win-ocr-helper]', c.toString().trim()))
    child.on('exit', (code) => {
      console.warn(`[win-ocr-helper] exited code=${code}`)
      this.handleExit()
    })
    child.on('error', (e) => {
      if ((e as NodeJS.ErrnoException).code === 'ENOENT') {
        if (!this.unavailable) {
          console.error(
            '[win-ocr-helper] binary not found — OCR / screen-reading is DISABLED. ' +
              'Build it once with: pnpm run build:ocr-helper  (needs .NET SDK). ' +
              `(${e.message})`
          )
        }
        this.unavailable = true
      } else {
        console.error('[win-ocr-helper] spawn error:', e.message)
      }
      this.handleExit()
    })
    // Successful start — reset backoff after a short grace period.
    setTimeout(() => {
      if (this.child === child) this.backoff = 500
    }, 2000)
  }

  private handleExit(): void {
    this.child = null
    // Fail every in-flight request; the helper restarts lazily on next request.
    while (this.queue.length) {
      const p = this.queue.shift()!
      clearTimeout(p.timer)
      p.reject(new Error('helper exited'))
    }
    this.backoff = Math.min(this.backoff * 2, MAX_BACKOFF_MS)
  }

  private recycle(): void {
    if (this.child) {
      try {
        this.child.kill()
      } catch {
        /* already dead */
      }
    }
    this.handleExit()
  }

  private request(opcode: number, payload: Buffer): Promise<string> {
    if (this.unavailable) return Promise.reject(new Error('helper unavailable (binary missing)'))
    this.ensureStarted()
    const child = this.child
    if (!child) return Promise.reject(new Error('helper not available'))
    return new Promise<string>((resolve, reject) => {
      const timer = setTimeout(() => {
        // Drop the wedged request and recycle the process.
        const idx = this.queue.findIndex((p) => p.timer === timer)
        if (idx >= 0) this.queue.splice(idx, 1)
        reject(new Error('helper request timed out'))
        this.recycle()
      }, REQUEST_TIMEOUT_MS)
      this.queue.push({ resolve, reject, timer })
      child.stdin.write(encodeRequest(opcode, payload))
    })
  }

  async ocr(jpeg: Buffer): Promise<OcrResult> {
    try {
      const json = await this.request(OP_OCR, jpeg)
      return JSON.parse(json) as OcrResult
    } catch (e) {
      return { ok: false, code: 'HELPER_ERROR', message: (e as Error).message }
    }
  }

  async windowInfo(): Promise<WindowInfo> {
    const json = await this.request(OP_WINDOW, Buffer.alloc(0))
    return JSON.parse(json) as WindowInfo
  }

  dispose(): void {
    this.recycle()
  }
}

export const helperProcess = new HelperProcess()
