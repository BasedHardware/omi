import { spawn, type ChildProcessWithoutNullStreams } from 'child_process'
import { resolveAudioHelperPath } from './resolveHelperPath'
import { encodeRequest, FrameDecoder } from '../ocr/helperProtocol'
import { OP_MUTE, OP_RESTORE, OP_HELLO, PROTOCOL_VERSION } from './protocol'
import { captureMessage } from '../sentry'
import { recordVoiceFlight } from '../voice/flightRecorder'

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
//   * THE USER IS NEVER LEFT MUTED. The endpoint mute is persistent OS state that
//     outlives the helper, so a helper that dies holding one would strand the
//     user's speakers muted. The helper restores on stdin EOF / exit (so an app
//     quit or crash self-heals), we shut it down gracefully rather than
//     TerminateProcess-ing it (which would skip that), and if it dies anyway we
//     re-spawn and replay RESTORE with the device id we watched it mute.

const REQUEST_TIMEOUT_MS = 4000
const MAX_BACKOFF_MS = 10000
// Grace for a recycled helper to see stdin EOF, unmute, and exit on its own
// before we resort to a hard kill (which would skip its restore).
const SHUTDOWN_GRACE_MS = 1500
// Bound the re-spawn attempts to heal a stranded mute, so a helper that dies on
// every launch can't become a spawn loop.
const MAX_STRANDED_RECOVERIES = 3

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
  // The endpoint id the helper told us it muted (null = we believe nothing is
  // muted). Survives the helper process, which is the whole point: it's what lets
  // us un-strand a mute whose helper died before it could restore.
  private heldDeviceId: string | null = null
  private strandedRecoveries = 0
  // Set on app quit — stops the recovery path from re-spawning a helper into a
  // shutting-down app (the graceful stdin close already makes it self-unmute).
  private disposed = false

  private ensureStarted(): void {
    if (this.child || this.unavailable || this.disposed) return
    const exe = resolveAudioHelperPath()
    // windowsHide: the helper is a console-subsystem .NET exe (OutputType=Exe).
    // Electron main is a GUI process with no console, so without CREATE_NO_WINDOW
    // the child allocates a NEW visible console — a stray taskbar window. Its
    // stdio is piped, so hiding the console loses nothing.
    const child = spawn(exe, [], { stdio: ['pipe', 'pipe', 'pipe'], windowsHide: true })
    this.child = child

    const decoder = new FrameDecoder((json) => {
      const pending = this.queue.shift()
      if (!pending) return
      clearTimeout(pending.timer)
      pending.resolve(json)
    })
    child.stdout.on('data', (chunk: Buffer) => decoder.push(chunk))
    child.stderr.on('data', (c: Buffer) => console.log('[win-audio-helper]', c.toString().trim()))
    // Both handlers ignore a child we've already torn down (recycle() nulls
    // `this.child` first), so a recycle + its trailing 'exit' can't double-count.
    child.on('exit', (code) => {
      if (this.child !== child) return
      console.warn(`[win-audio-helper] exited code=${code}`)
      this.handleExit()
    })
    child.on('error', (e) => {
      if (this.child !== child) return
      if ((e as NodeJS.ErrnoException).code === 'ENOENT') {
        if (!this.unavailable) {
          console.error(
            '[win-audio-helper] binary not found — PTT system-audio muting is DISABLED. ' +
              'Build it once with: pwsh scripts/build-audio-helper.ps1  (needs .NET SDK). ' +
              `(${e.message})`
          )
          // Durable signal: a field user's "PTT doesn't mute my music" otherwise
          // records nothing. Inside the !unavailable guard, so it fires at most once.
          // TODO(#10240 track3): route through a Windows main-process recordFallback emitter
          // as outcome:'degraded' once one exists (see warnDegraded note in
          // src/main/assistants/aiUserProfile/orchestrate.ts:46-52). Until then
          // captureMessage is the correct call (Sentry for developer-facing degrades).
          captureMessage('win-audio-helper binary not found — PTT system-audio mute disabled', {
            area: 'ptt-audio-mute',
            level: 'warning',
            extra: { reason: 'enoent' }
          })
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
    // before any real request (FIFO) so it resolves first.
    void this.handshake()
  }

  private async handshake(): Promise<void> {
    try {
      const json = await this.request(OP_HELLO, '{}')
      const { protocolVersion } = JSON.parse(json) as { protocolVersion?: number }
      if (protocolVersion !== PROTOCOL_VERSION) {
        // A stale helper build (someone pulled without re-running install). We
        // DISABLE muting rather than drive it: a pre-v3 helper doesn't unmute on
        // exit and doesn't report the device it muted, so muting through it can
        // strand the user's speakers muted with no way back. No muting is a
        // cosmetic loss; a stranded mute is not.
        console.error(
          `[win-audio-helper] PROTOCOL MISMATCH: helper=${protocolVersion} expected=${PROTOCOL_VERSION} — ` +
            'PTT system-audio muting is DISABLED until you rebuild it ' +
            '(npm run build:audio-helper).'
        )
        if (!this.unavailable) {
          // Durable signal for a stale helper build in the field. Guarded so it
          // fires at most once (before we latch unavailable below).
          // TODO(#10240 track3): route through a Windows main-process recordFallback emitter
          // as outcome:'degraded' once one exists (see warnDegraded note in
          // src/main/assistants/aiUserProfile/orchestrate.ts:46-52). Until then
          // captureMessage is the correct call (Sentry for developer-facing degrades).
          captureMessage('win-audio-helper protocol mismatch — PTT system-audio mute disabled', {
            area: 'ptt-audio-mute',
            level: 'warning',
            extra: {
              reason: 'protocol_mismatch',
              helper: protocolVersion,
              expected: PROTOCOL_VERSION
            }
          })
        }
        this.unavailable = true
        this.recycle()
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
    this.recoverStrandedMute()
  }

  /** The helper died while we believe it held a mute. Its `finally` normally
   *  unmutes on the way out, but a hard kill (TerminateProcess) skips that — and
   *  the mute is persistent OS state, so the user would be left with silent
   *  speakers. Re-spawn and replay RESTORE with the id we watched it mute; the
   *  helper's hint path unmutes exactly that endpoint. */
  private recoverStrandedMute(): void {
    if (!this.heldDeviceId || this.unavailable || this.disposed) return
    if (this.strandedRecoveries >= MAX_STRANDED_RECOVERIES) {
      console.error(
        `[win-audio-helper] GAVE UP restoring a stranded mute on ${this.heldDeviceId} after ` +
          `${MAX_STRANDED_RECOVERIES} attempts — the user may need to unmute manually.`
      )
      return
    }
    this.strandedRecoveries++
    console.warn(
      `[win-audio-helper] helper died holding a mute — re-spawning to restore ${this.heldDeviceId} ` +
        `(attempt ${this.strandedRecoveries}/${MAX_STRANDED_RECOVERIES})`
    )
    const timer = setTimeout(() => void this.restoreSystemAudio(), this.backoff)
    timer.unref?.()
  }

  /** Shut the helper down so it can run its own restore. We deliberately do NOT
   *  kill first: TerminateProcess skips the helper's unmute-on-exit and would
   *  strand the mute. Closing stdin gives it EOF; the kill is only a backstop for
   *  a wedged helper that never gets there. */
  private recycle(): void {
    const child = this.child
    this.handleExit() // nulls this.child, so the trailing 'exit' is ignored
    if (!child) return
    try {
      child.stdin.end()
    } catch {
      /* pipe already gone */
    }
    const kill = setTimeout(() => {
      try {
        child.kill()
      } catch {
        /* already dead */
      }
    }, SHUTDOWN_GRACE_MS)
    kill.unref?.()
    child.once('exit', () => clearTimeout(kill))
  }

  private request(opcode: number, payloadJson: string): Promise<string> {
    if (this.unavailable) return Promise.reject(new Error('helper unavailable (binary missing)'))
    if (this.disposed) return Promise.reject(new Error('helper disposed (app quitting)'))
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

  /** Is an endpoint mute currently held? (INV-VOICE-1: this must never be true
   *  while a reply playback window is active — see main/voice/invariants.ts.) */
  isHoldingMute(): boolean {
    return this.heldDeviceId !== null
  }

  /** Mute the default output device (gated helper-side on audio-is-playing +
   *  not-already-user-muted, idempotent). Fire-and-forget: never throws, never
   *  blocks PTT — a missing/dead helper is swallowed. */
  async muteSystemAudio(): Promise<void> {
    try {
      const json = await this.request(OP_MUTE, '{}')
      // A refusal is a legitimate no-op (nothing playing / the user muted the
      // device themselves), but a SILENT one is unexplainable in the field
      // ("PTT doesn't mute my music") — so say why, with the peak we measured.
      const res = JSON.parse(json) as {
        muted?: boolean
        reason?: string
        peak?: number
        deviceId?: string
      }
      if (res.muted && res.deviceId) {
        // Remember WHAT we muted: if the helper is killed before it can restore,
        // this id is the only way back to the user's audio.
        this.heldDeviceId = res.deviceId
        // Flight-record the ENGAGED endpoint mute: it silences the default
        // output device, so its overlap with reply playback is exactly the
        // evidence the 2026-07-18 muted-reply failure needed (device id only —
        // an opaque endpoint GUID, no PII).
        recordVoiceFlight('main', 'system_audio', { action: 'mute', engaged: true })
      } else if (!res.muted && res.reason) {
        console.log(`[win-audio-helper] mute skipped: ${res.reason} (peak=${res.peak ?? 0})`)
        recordVoiceFlight('main', 'system_audio', {
          action: 'mute',
          engaged: false,
          reason: res.reason
        })
      }
    } catch {
      /* helper missing / dead / slow — muting is best-effort, never blocks PTT */
    }
  }

  /** Restore whatever muteSystemAudio muted. Unconditional + idempotent. Carries
   *  the held device id so a FRESH helper (the previous one having been killed
   *  mid-mute) can still unmute the exact endpoint we muted. */
  async restoreSystemAudio(): Promise<void> {
    const deviceId = this.heldDeviceId
    try {
      await this.request(OP_RESTORE, JSON.stringify(deviceId ? { deviceId } : {}))
      // Only clear once the helper has confirmed — a rejected restore must leave
      // heldDeviceId set so the recovery path can retry it.
      if (deviceId !== null) {
        recordVoiceFlight('main', 'system_audio', { action: 'restore', held: true })
      }
      this.heldDeviceId = null
      this.strandedRecoveries = 0
    } catch {
      /* helper missing / dead — the exit path re-spawns and retries the restore */
    }
  }

  dispose(): void {
    // Suppress recovery re-spawns: we're shutting down, and closing stdin makes
    // the helper unmute itself on the way out (its exit `finally`).
    this.disposed = true
    this.recycle()
  }
}

export const systemAudioMuteBridge = new SystemAudioMuteBridge()
