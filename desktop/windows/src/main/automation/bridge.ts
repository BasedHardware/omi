import { spawn, type ChildProcessWithoutNullStreams } from 'child_process'
import { resolveHelperPath } from './resolveHelperPath'
import { encodeRequest, FrameDecoder } from '../ocr/helperProtocol'
import { OP_SNAPSHOT, OP_STEP, OP_HELLO, PROTOCOL_VERSION } from './protocol'
import { validatePlan } from './capabilities'
import type { AutomationPlan, PlanRunResult, StepResult, UiSnapshot } from '../../shared/types'

const REQUEST_TIMEOUT_MS = 8000
const MAX_BACKOFF_MS = 10000

type Pending = { resolve: (json: string) => void; reject: (e: Error) => void; timer: NodeJS.Timeout }

class AutomationBridge {
  private child: ChildProcessWithoutNullStreams | null = null
  private readonly queue: Pending[] = []
  private backoff = 500

  private ensureStarted(): void {
    if (this.child) return
    const exe = resolveHelperPath()
    const child = spawn(exe, [], { stdio: ['pipe', 'pipe', 'pipe'] })
    this.child = child

    const decoder = new FrameDecoder((json) => {
      const pending = this.queue.shift()
      if (!pending) return
      clearTimeout(pending.timer)
      pending.resolve(json)
    })
    child.stdout.on('data', (chunk: Buffer) => decoder.push(chunk))
    child.stderr.on('data', (c: Buffer) =>
      console.log('[win-automation-helper]', c.toString().trim())
    )
    child.on('exit', (code) => {
      console.warn(`[win-automation-helper] exited code=${code}`)
      this.handleExit()
    })
    child.on('error', (e) => {
      console.error('[win-automation-helper] spawn error:', e.message)
      this.handleExit()
    })
    setTimeout(() => {
      if (this.child === child) this.backoff = 500
    }, 2000)

    // Assert the helper speaks our protocol version. Fire-and-forget: queued
    // before any real request (FIFO), so the version check resolves first. A
    // mismatch means a stale helper build — log loudly; we don't recycle (that
    // would loop) since a rebuild is the only fix.
    void this.handshake()
  }

  private async handshake(): Promise<void> {
    try {
      const json = await this.request(OP_HELLO, '{}')
      const { protocolVersion } = JSON.parse(json) as { protocolVersion?: number }
      if (protocolVersion !== PROTOCOL_VERSION) {
        console.error(
          `[win-automation-helper] PROTOCOL MISMATCH: helper=${protocolVersion} expected=${PROTOCOL_VERSION} — rebuild the helper (pwsh scripts/build-automation-helper.ps1)`
        )
      }
    } catch (e) {
      console.warn('[win-automation-helper] handshake failed:', (e as Error).message)
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

  async snapshot(windowHandle?: string): Promise<UiSnapshot> {
    try {
      const json = await this.request(OP_SNAPSHOT, JSON.stringify({ windowHandle: windowHandle ?? '' }))
      return JSON.parse(json) as UiSnapshot
    } catch (e) {
      return { ok: false, code: 'HELPER_ERROR', message: (e as Error).message }
    }
  }

  // Validate, then run steps sequentially. `onStep` streams progress; the first
  // failure halts the plan. Validation failure aborts before any step runs.
  async run(plan: AutomationPlan, onStep: (r: StepResult) => void): Promise<PlanRunResult> {
    const check = validatePlan(plan)
    if (!check.ok) return { planId: plan.id, ok: false, message: `rejected: ${check.reason}` }

    for (let i = 0; i < plan.steps.length; i++) {
      onStep({ planId: plan.id, stepIndex: i, status: 'running' })
      let res: { ok: boolean; message?: string }
      try {
        const json = await this.request(OP_STEP, JSON.stringify(plan.steps[i]))
        res = JSON.parse(json) as { ok: boolean; message?: string }
      } catch (e) {
        res = { ok: false, message: (e as Error).message }
      }
      if (!res.ok) {
        onStep({ planId: plan.id, stepIndex: i, status: 'failed', detail: res.message })
        return { planId: plan.id, ok: false, failedStepIndex: i, message: res.message }
      }
      onStep({ planId: plan.id, stepIndex: i, status: 'ok' })
    }
    return { planId: plan.id, ok: true }
  }

  dispose(): void {
    this.recycle()
  }
}

export const automationBridge = new AutomationBridge()
