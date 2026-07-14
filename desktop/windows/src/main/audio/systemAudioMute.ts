import { spawn, type ChildProcessWithoutNullStreams } from 'child_process'
import { resolveAudioHelperPath } from './resolveHelperPath'
import { encodeRequest, FrameDecoder } from '../ocr/helperProtocol'
import { OP_MUTE, OP_RESTORE, OP_HELLO, PROTOCOL_VERSION } from './protocol'

// Track-2-owned bridge to win-audio-helper.exe — mutes the default output device
// while push-to-talk is capturing (macOS SystemAudioMuteController parity, ported
// as a WASAPI helper because src/main has no COM/vtable precedent). Copies the
// automation bridge's persistent-child + length-prefixed-frame + crash-backoff
// shape, trimmed to two fire-and-forget verbs (MUTE / RESTORE).
//
// Design guarantees the PTT path depends on:
//   * Warm-spawned at app startup so PTT-down never eats a cold-spawn penalty.
//   * If the helper binary is absent (no .NET SDK at build) every call no-ops
//     silently and NEVER blocks or delays PTT.
//   * mute/restore never throw to the caller — a hung/dead helper is swallowed.

const REQUEST_TIMEOUT_MS = 4000
const MAX_BACKOFF_MS = 10000

type Pending = {
  resolve: (json: string) => void
  reject: (e: Error) => void
  timer: NodeJS.Timeout
}

class SystemAudioMuteBridge {
  private child: ChildProcessWithoutNullStreams | null = null
  private readonly queue: Pending[] = []
  private backoff = 500
  // Set once the helper binary is confirmed missing (spawn ENOENT). Without it,
  // every mute/restore re-spawns the missing exe — failing forever and flooding
  // the log. Once unavailable, fail fast + silent. A rebuild + app restart clears
  // it. (Mirrors the automation/OCR bridges.)
  private unavailable = false

  private ensureStarted(): void {
    if (this.child || this.unavailable) return
    const exe = resolveAudioHelperPath()
    const child = spawn(exe, [], { stdio: ['pipe', 'pipe', 'pipe'] })
    this.child = child

    const decoder = new FrameDecoder((json) => {
      const pending = this.queue.shift()
      if (!pending) return
      clearTimeout(pending.timer)
      pending.resolve(json)
    })
    child.stdout.on('data', (chunk: Buffer) => decoder.push(chunk))
    child.stderr.on('data', (c: Buffer) => console.log('[win-audio-helper]', c.toString().trim()))
    child.on('exit', (code) => {
      console.warn(`[win-audio-helper] exited code=${code}`)
      this.handleExit()
    })
    child.on('error', (e) => {
      if ((e as NodeJS.ErrnoException).code === 'ENOENT') {
        if (!this.unavailable) {
          console.error(
            '[win-audio-helper] binary not found — PTT system-audio muting is DISABLED. ' +
              'Build it once with: pwsh scripts/build-audio-helper.ps1  (needs .NET SDK). ' +
              `(${e.message})`
          )
        }
        this.unavailable = true
      } else {
        console.error('[win-audio-helper] spawn error:', e.message)
      }
      this.handleExit()
    })
    setTimeout(() => {
      if (this.child === child) this.backoff = 500
    }, 2000)

    // Assert the helper speaks our protocol version. Fire-and-forget, queued
    // before any real request (FIFO) so it resolves first. A mismatch means a
    // stale helper build — log loudly; we don't recycle (a rebuild is the fix).
    void this.handshake()
  }

  private async handshake(): Promise<void> {
    try {
      const json = await this.request(OP_HELLO, '{}')
      const { protocolVersion } = JSON.parse(json) as { protocolVersion?: number }
      if (protocolVersion !== PROTOCOL_VERSION) {
        console.error(
          `[win-audio-helper] PROTOCOL MISMATCH: helper=${protocolVersion} expected=${PROTOCOL_VERSION} — rebuild the helper (pwsh scripts/build-audio-helper.ps1)`
        )
      }
    } catch (e) {
      console.warn('[win-audio-helper] handshake failed:', (e as Error).message)
    }
  }

  private handleExit(): void {
    this.child = null
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

  private request(opcode: number, payloadJson: string): Promise<string> {
    if (this.unavailable) return Promise.reject(new Error('helper unavailable (binary missing)'))
    this.ensureStarted()
    const child = this.child
    if (!child) return Promise.reject(new Error('helper not available'))
    return new Promise<string>((resolve, reject) => {
      const timer = setTimeout(() => {
        const idx = this.queue.findIndex((p) => p.timer === timer)
        if (idx >= 0) this.queue.splice(idx, 1)
        reject(new Error('helper request timed out'))
        this.recycle()
      }, REQUEST_TIMEOUT_MS)
      this.queue.push({ resolve, reject, timer })
      child.stdin.write(encodeRequest(opcode, Buffer.from(payloadJson, 'utf8')))
    })
  }

  /** Eagerly spawn the helper (app startup) so the first PTT-down mute doesn't pay
   *  the cold-spawn cost. No-op when the binary is missing. */
  warm(): void {
    this.ensureStarted()
  }

  /** Mute the default output device (gated helper-side on audio-is-playing +
   *  not-already-user-muted, idempotent). Fire-and-forget: never throws, never
   *  blocks PTT — a missing/dead helper is swallowed. */
  async muteSystemAudio(): Promise<void> {
    try {
      await this.request(OP_MUTE, '{}')
    } catch {
      /* helper missing / dead / slow — muting is best-effort, never blocks PTT */
    }
  }

  /** Restore whatever muteSystemAudio muted. Unconditional + idempotent. */
  async restoreSystemAudio(): Promise<void> {
    try {
      await this.request(OP_RESTORE, '{}')
    } catch {
      /* helper missing / dead — nothing to restore */
    }
  }

  dispose(): void {
    this.recycle()
  }
}

export const systemAudioMuteBridge = new SystemAudioMuteBridge()
