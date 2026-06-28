import { ipcMain, dialog, BrowserWindow } from 'electron'
import { automationBridge } from '../automation/bridge'
import { getAutomationTargetHandle } from '../automation/foregroundTarget'
import { withAgentActive } from '../agentActivity'
import { isPaymentSensitive } from '../../shared/paymentGuard'
import type { AutomationPlan, AutomationStep, UiSnapshot } from '../../shared/types'

// Result of the native-dialog confirm flow. `canceled` distinguishes a user
// "Cancel" from an execution failure.
export type ConfirmRunResult = { ok: boolean; canceled?: boolean; message?: string }

// Human-readable, consent-relevant summary of a step for the native dialog.
// Built in MAIN from the real plan (not renderer-supplied text) so what the user
// approves is what runs. Element refs aren't human-friendly, so clicks are
// described generically; the typed value / keys (what matters for consent) shown.
function describeStepForDialog(step: AutomationStep, i: number): string {
  const n = `${i + 1}. `
  switch (step.type) {
    case 'focus_window':
      return `${n}Bring the target window to the front`
    case 'set_value':
      return `${n}Type “${step.value}”`
    case 'send_keys':
      return `${n}Press keys: ${step.keys}`
    case 'invoke_element':
    case 'click':
      return `${n}Click an element`
    case 'select_item':
      return `${n}Select an item`
    case 'toggle':
      return `${n}Turn a setting ${step.state ? 'on' : 'off'}`
    case 'wait_for':
      return `${n}Wait for an element`
    default:
      return `${n}${(step as { type: string }).type}`
  }
}

export function registerAutomationHandlers(): void {
  ipcMain.handle('automation:snapshot', async (_e, windowHandle?: string): Promise<UiSnapshot> => {
    return automationBridge.snapshot(windowHandle)
  })

  // The last non-Omi foreground window the planner should target (null → caller
  // falls back to the live foreground window).
  ipcMain.handle('automation:targetWindow', async (): Promise<string | null> => {
    return getAutomationTargetHandle()
  })

  // The only run path is the consent-gated automation:confirmRun below. The
  // former dialog-less 'automation:run' IPC was removed: it was exposed to the
  // renderer but had no legitimate caller, and let web content drive Windows UI
  // input with no approval. Per-step progress events aren't needed by the
  // confirm flow (it resolves once on completion).

  // Run a plan. Cortex's agent is autonomous by default: ordinary plans run in
  // the BACKGROUND (no focus stealing) while the screen edges glow blue, without
  // interrupting the user. The one exception is PAYMENT-sensitive plans
  // (checkout / card / purchase) — those always stop and require explicit
  // approval via a native dialog before anything runs.
  ipcMain.handle(
    'automation:confirmRun',
    async (e, plan: AutomationPlan): Promise<ConfirmRunResult> => {
      if (isPaymentSensitive(plan)) {
        const parent = BrowserWindow.fromWebContents(e.sender)
        const detail = [
          'This looks like a payment. Cortex will not do this without you.',
          '',
          `In “${plan.targetWindow}”:`,
          '',
          ...plan.steps.map((s, i) => describeStepForDialog(s, i))
        ].join('\n')
        const opts = {
          type: 'warning' as const,
          title: 'Cortex — approve payment',
          message: plan.summary || `Cortex wants to complete a payment in “${plan.targetWindow}”`,
          detail,
          buttons: ['Approve & pay', 'Cancel'],
          defaultId: 1,
          cancelId: 1,
          noLink: true
        }
        const { response } = parent
          ? await dialog.showMessageBox(parent, opts)
          : await dialog.showMessageBox(opts)
        if (response !== 0) return { ok: false, canceled: true }
      }

      // Non-payment (or approved payment): run in the background with the blue
      // edge glow up for the duration.
      const result = await withAgentActive(() => automationBridge.run(plan, () => {}))
      return { ok: result.ok, message: result.message }
    }
  )
}
