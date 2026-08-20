/**
 * End-to-end harness for the desktop-automation PLANNER path.
 *
 * The unit tests mock the LLM + snapshot, so the one thing they can't prove is
 * the real round-trip: live UIA snapshot of a real window → real LLM call →
 * structured plan → capability validation. This file exercises exactly that,
 * reusing the SAME planner code the app runs (classifyIntent + planActions),
 * just with node-side deps wired in place of Electron IPC / firebase auth.
 *
 * It is GATED on a Firebase ID token and skips entirely without one, so it never
 * runs during a normal `npm test`. To run it:
 *
 *   # token: in the running app's devtools → await auth.currentUser.getIdToken()
 *   $env:AUTOMATION_E2E_TOKEN="<id-token>"        # required (expires ~1h)
 *   $env:AUTOMATION_E2E_INSTRUCTION="type 'hello world' into the document"  # optional
 *   $env:AUTOMATION_E2E_TARGET_PROC="notepad"     # optional, launched if not running
 *   $env:AUTOMATION_E2E_EXECUTE="1"               # optional: ALSO run the steps for real
 *   npx vitest run src/main/automation/planner.e2e.test.ts
 *
 * Default (no EXECUTE flag) is read-only: it plans + validates but does NOT
 * touch the target app. Set AUTOMATION_E2E_EXECUTE=1 to close the loop and
 * actually drive the window (bring the target to the foreground first).
 */
import { spawn, execSync, type ChildProcessWithoutNullStreams } from 'child_process'
import { join } from 'path'
import axios from 'axios'
import { describe, it, expect } from 'vitest'
import { encodeRequest, FrameDecoder } from '../ocr/helperProtocol'
import { OP_SNAPSHOT, OP_STEP } from './protocol'
import { validatePlan } from './capabilities'
import { looksLikeAction, planActions } from '../../renderer/src/lib/actionPlanner'
import { describePlanSteps } from '../../renderer/src/lib/automationPlan'
import { parseMessagesSse } from '../../renderer/src/lib/messagesSse'
import type { AutomationPlan, UiSnapshot } from '../../shared/types'

const TOKEN = process.env.AUTOMATION_E2E_TOKEN ?? ''
const INSTRUCTION =
  process.env.AUTOMATION_E2E_INSTRUCTION ?? "type 'hello world' into the document"
const TARGET_PROC = process.env.AUTOMATION_E2E_TARGET_PROC ?? 'notepad'
const EXECUTE = process.env.AUTOMATION_E2E_EXECUTE === '1'
// Token-free execution check: run a hand-built plan through the real helper to
// prove the C# step handlers + bridge run loop actually drive a window. Gated
// separately from the (LLM) planner test so it can run while the LLM is
// quota-blocked. Verified by a screenshot taken right after the run.
const EXEC = process.env.AUTOMATION_E2E_EXEC === '1'
// Mixed case + shifted symbols (but none of the ^ % + # chars capabilities.ts
// forbids) so the screenshot proves send_keys preserves case/symbols.
const EXEC_MARKER = 'OmiKbd-Verify!@2026'
const DESKTOP_BASE =
  process.env.VITE_OMI_DESKTOP_API_BASE ?? 'https://desktop-backend-hhibjajaja-uc.a.run.app'
const AGENT_MODEL = 'claude-haiku-4-5-20251001'
const HELPER = join(
  process.cwd(),
  'resources',
  'win-automation-helper',
  'win-automation-helper.exe'
)

// Minimal persistent stdio bridge to the helper — a node-side mirror of
// bridge.ts (which can't be imported here: it pulls in electron). One process,
// one in-flight request at a time, length-prefixed frames.
class HelperClient {
  private child: ChildProcessWithoutNullStreams
  private readonly queue: Array<(json: string) => void> = []
  constructor() {
    this.child = spawn(HELPER, [], { stdio: ['pipe', 'pipe', 'pipe'] })
    const decoder = new FrameDecoder((json) => this.queue.shift()?.(json))
    this.child.stdout.on('data', (c: Buffer) => decoder.push(c))
    this.child.stderr.on('data', (c: Buffer) => console.log('[helper]', c.toString().trim()))
  }
  request(opcode: number, payload: object): Promise<string> {
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error('helper timed out')), 8000)
      this.queue.push((json) => {
        clearTimeout(timer)
        resolve(json)
      })
      this.child.stdin.write(encodeRequest(opcode, Buffer.from(JSON.stringify(payload), 'utf8')))
    })
  }
  dispose(): void {
    this.child.kill()
  }
}

// Find the target app's top-level window handle (decimal, as the helper parses
// it). Launch the process first if it isn't already running.
function resolveTargetHandle(proc: string): string {
  const ps = (script: string): string =>
    execSync(`powershell -NoProfile -Command "${script}"`, { encoding: 'utf8' }).trim()
  const query = `(Get-Process ${proc} -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1).MainWindowHandle`
  let handle = ps(query)
  if (!handle || handle === '0') {
    console.log(`[harness] launching ${proc}…`)
    execSync(`powershell -NoProfile -Command "Start-Process ${proc}"`)
    for (let i = 0; i < 20 && (!handle || handle === '0'); i++) {
      execSync('powershell -NoProfile -Command "Start-Sleep -Milliseconds 300"')
      handle = ps(query)
    }
  }
  if (!handle || handle === '0') throw new Error(`could not get a window handle for "${proc}"`)
  return handle
}

const sleep = (ms: number): Promise<void> => new Promise((r) => setTimeout(r, ms))
const OMI_BASE = process.env.VITE_OMI_API_BASE ?? 'https://api.omi.me'

// Real LLM call — mirrors the app's agentLLM.ts (incl. its 429 fallback), with
// the supplied Firebase ID token instead of firebase-sdk auth. The desktop
// /v2/chat/completions endpoint is rate-limited per-account, so on 429 we fall
// back to /v2/messages (separate limit) exactly like the app now does.
async function callAgentLLM(prompt: string): Promise<string> {
  try {
    const res = await axios.post(
      `${DESKTOP_BASE}/v2/chat/completions`,
      { model: AGENT_MODEL, stream: false, messages: [{ role: 'user', content: prompt }] },
      { headers: { Authorization: `Bearer ${TOKEN}` }, timeout: 20000 }
    )
    return res.data?.choices?.[0]?.message?.content ?? ''
  } catch (e) {
    const status = axios.isAxiosError(e) ? e.response?.status : undefined
    if (status === 429 || (axios.isAxiosError(e) && !e.response)) {
      console.log('[harness] /v2/chat/completions 429 → falling back to /v2/messages')
      const res = await axios.post(
        `${OMI_BASE}/v2/messages`,
        { text: prompt },
        { headers: { Authorization: `Bearer ${TOKEN}` }, responseType: 'text', timeout: 30000 }
      )
      return parseMessagesSse(String(res.data ?? ''))
    }
    throw e
  }
}

describe.skipIf(!TOKEN)('automation planner e2e', () => {
  it('snapshots a real window, plans via real LLM, and validates the plan', async () => {
    const handle = resolveTargetHandle(TARGET_PROC)
    console.log(`[harness] target "${TARGET_PROC}" handle=${handle}`)
    const helper = new HelperClient()
    try {
      const getSnapshot = async (): Promise<UiSnapshot> => {
        const json = await helper.request(OP_SNAPSHOT, { windowHandle: handle })
        return JSON.parse(json) as UiSnapshot
      }

      // 1. Snapshot — prove UIA reading works against a real window.
      const snap = await getSnapshot()
      console.log('\n=== SNAPSHOT ===')
      if (!snap.ok) throw new Error(`snapshot failed: ${snap.message}`)
      console.log(`window: "${snap.window.title}" (${snap.window.processName})`)
      console.log(`elements: ${JSON.stringify(snap.elements).length} bytes of tree`)
      expect(snap.ok).toBe(true)

      // 2. Intent gate — the free keyword pre-filter should flag our instruction.
      console.log(`\n=== INTENT === "${INSTRUCTION}" → looksLikeAction=${looksLikeAction(INSTRUCTION)}`)
      expect(looksLikeAction(INSTRUCTION)).toBe(true)

      // 3. Plan — the real LLM round-trip producing a structured plan.
      const result = await planActions(INSTRUCTION, { getSnapshot, callLLM: callAgentLLM })
      console.log('\n=== PLAN ===')
      if (!result.ok) throw new Error(`planning failed: ${result.reason}`)
      console.log(`summary: ${result.plan.summary}`)
      console.log(`targetWindow: ${result.plan.targetWindow}`)
      console.log(describePlanSteps(result.plan.steps).join('\n'))
      expect(result.ok).toBe(true)

      // 4. Validate — same capability gate the bridge runs before dispatch.
      const check = validatePlan(result.plan)
      console.log(`\n=== VALIDATION === ${check.ok ? 'OK' : 'REJECTED: ' + check.reason}`)
      expect(check.ok).toBe(true)

      // 5. (opt-in) Execute — actually drive the window, streaming step status.
      if (EXECUTE) {
        console.log('\n=== EXECUTE ===')
        for (let i = 0; i < result.plan.steps.length; i++) {
          const json = await helper.request(OP_STEP, result.plan.steps[i])
          const r = JSON.parse(json) as { ok: boolean; message?: string }
          console.log(`step ${i} (${result.plan.steps[i].type}): ${r.ok ? 'ok' : 'FAILED ' + r.message}`)
          expect(r.ok).toBe(true)
        }
      }
    } finally {
      helper.dispose()
    }
  }, 360000)
})

describe.skipIf(!EXEC)('automation execution e2e (no LLM)', () => {
  it('executes a hand-built plan against a real window', async () => {
    // AUTOMATION_E2E_HANDLE lets a caller target a specific window (e.g. a
    // readable WinForms TextBox) instead of launching TARGET_PROC by name.
    const handle = process.env.AUTOMATION_E2E_HANDLE || resolveTargetHandle(TARGET_PROC)
    console.log(`[harness] target "${TARGET_PROC}" handle=${handle}`)
    // focus the real window by handle, then type a recognizable marker on its
    // own line. Uses only allowlisted steps/keys (validates clean).
    const plan: AutomationPlan = {
      id: 'exec-e2e',
      summary: `type ${EXEC_MARKER} into ${TARGET_PROC}`,
      targetWindow: 'Notepad',
      steps: [
        { type: 'focus_window', windowRef: handle },
        { type: 'send_keys', keys: `{ENTER}${EXEC_MARKER}{ENTER}` }
      ]
    }

    const check = validatePlan(plan)
    console.log(`\n=== VALIDATION === ${check.ok ? 'OK' : 'REJECTED: ' + check.reason}`)
    expect(check.ok).toBe(true)

    const helper = new HelperClient()
    try {
      console.log('\n=== EXECUTE ===')
      for (let i = 0; i < plan.steps.length; i++) {
        const json = await helper.request(OP_STEP, plan.steps[i])
        const r = JSON.parse(json) as { ok: boolean; message?: string }
        console.log(`step ${i} (${plan.steps[i].type}): ${r.ok ? 'ok' : 'FAILED ' + r.message}`)
        expect(r.ok).toBe(true)
        await sleep(500) // let focus + keystrokes settle between steps
      }
      // Capture proof WHILE the target is still foregrounded by the run — once
      // this test process exits, the shell regains focus and the evidence is
      // gone. The marker should be visible in the captured window.
      execSync(
        `powershell -NoProfile -Command "Add-Type -AssemblyName System.Windows.Forms,System.Drawing; $b=[System.Windows.Forms.SystemInformation]::VirtualScreen; $bmp=New-Object System.Drawing.Bitmap $b.Width,$b.Height; $g=[System.Drawing.Graphics]::FromImage($bmp); $g.CopyFromScreen($b.Location,[System.Drawing.Point]::Empty,$b.Size); $bmp.Save((Join-Path $env:TEMP 'omi-exec-proof.png')); $g.Dispose(); $bmp.Dispose()"`
      )
      console.log(`\n=== PROOF === screenshot saved to %TEMP%\\omi-exec-proof.png (look for ${EXEC_MARKER})`)

      // Re-snapshot: best-effort log of the title (carries Notepad's first line).
      const after = JSON.parse(await helper.request(OP_SNAPSHOT, { windowHandle: handle })) as UiSnapshot
      if (after.ok) console.log(`=== POST-EXEC TITLE === ${after.window.title}`)
    } finally {
      helper.dispose()
    }
  }, 60000)
})

// Token-free snapshot characterization: dump the pruned UIA tree size + a sample
// of nodes for a target window, so we can see what real apps expose (e.g. WinUI
// apps returning an empty tree) before tuning the helper's pruning.
const SNAP = process.env.AUTOMATION_E2E_SNAPSHOT === '1'

describe.skipIf(!SNAP)('automation snapshot characterization (no LLM)', () => {
  it('snapshots a real window and reports the element tree', async () => {
    const handle = process.env.AUTOMATION_E2E_HANDLE || resolveTargetHandle(TARGET_PROC)
    const helper = new HelperClient()
    try {
      const snap = JSON.parse(await helper.request(OP_SNAPSHOT, { windowHandle: handle })) as UiSnapshot
      if (!snap.ok) throw new Error(`snapshot failed: ${snap.message}`)
      type N = (typeof snap.elements)[number]
      let count = 0
      const sample: string[] = []
      const walk = (els: N[], depth: number): void => {
        for (const el of els) {
          count++
          if (sample.length < 40) {
            sample.push(`${'  '.repeat(depth)}${el.ref} [${el.controlType}] "${el.name}" {${el.patterns.join(',')}}`)
          }
          if (el.children) walk(el.children, depth + 1)
        }
      }
      walk(snap.elements, 0)
      console.log(`\n=== SNAPSHOT: "${snap.window.title}" (${snap.window.processName}) ===`)
      console.log(`total elements: ${count}`)
      console.log(sample.join('\n'))
    } finally {
      helper.dispose()
    }
  }, 60000)
})
